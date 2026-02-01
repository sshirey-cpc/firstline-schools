"""Load users from Grow API to BigQuery (active users only)."""
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any
from pythonjsonlogger import jsonlogger

from config import Config
from auth import get_bearer_token, AuthenticationError
from api_client import GrowAPIClient, APIError
from bigquery_client import BigQueryClient, BigQueryError
from transformers_users import transform_user
from schema_users import SCHEMA, TABLE_NAME


def setup_logging() -> None:
    """Configure structured JSON logging."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class UsersAPIClient(GrowAPIClient):
    """Extended API client for fetching users."""

    def fetch_users(self, archived: bool = False):
        """
        Fetch users from API with pagination.

        Args:
            archived: If True, fetch archived users. If False, fetch active users only.

        Yields:
            Individual user records
        """
        url = f"{self.BASE_URL}/users"
        params = {"archived": str(archived).lower()}  # 'true' or 'false'

        page_num = 0
        total_fetched = 0
        pagination_type = None

        logger = logging.getLogger(__name__)
        logger.info(f"Starting to fetch {'archived' if archived else 'active'} users from Grow API")

        while True:
            page_num += 1
            logger.info(f"Fetching page {page_num} (total records so far: {total_fetched})")

            try:
                response = self._make_request(url, params)
            except Exception as e:
                logger.error(f"Failed to fetch page {page_num}: {str(e)}")
                raise

            # Detect pagination on first request
            if page_num == 1:
                pagination_type = self._detect_pagination_type(response)
                if pagination_type:
                    logger.info(f"Detected pagination type: {pagination_type}")
                else:
                    logger.info("No pagination detected, assuming single page response")

            # Extract records from response
            records = None
            if isinstance(response, list):
                records = response
            else:
                for key in ["data", "results", "items", "users", "records"]:
                    if key in response:
                        records = response[key]
                        break

            if records is None:
                logger.warning(f"Could not find records in response. Keys: {response.keys()}")
                break

            # Yield individual records
            for record in records:
                yield record
                total_fetched += 1

            logger.info(f"Page {page_num}: fetched {len(records)} records")

            # Check if there are more pages
            if not pagination_type:
                break

            # Get parameters for next page
            params = self._get_next_params(pagination_type, response, params, total_fetched)
            if not params:
                logger.info("Reached last page")
                break

            # Safety check: if we got 0 records, stop pagination
            if len(records) == 0:
                logger.info("Received empty page, stopping pagination")
                break

        logger.info(f"Finished fetching. Total records: {total_fetched}")


def main() -> None:
    """
    Main pipeline orchestrator for users data.

    Workflow:
    1. Load configuration from .env
    2. Authenticate with Grow API
    3. Initialize API and BigQuery clients
    4. Ensure BigQuery table exists
    5. Fetch users from API (archived=false)
    6. Transform each record
    7. Batch and load to BigQuery
    8. Log summary statistics
    """
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    start_time = datetime.utcnow()
    logger.info("=" * 60)
    logger.info("Starting Grow API Users to BigQuery pipeline")
    logger.info("=" * 60)

    try:
        # 1. Load configuration
        logger.info("Loading configuration from .env")
        config = Config.load()
        logger.info(
            "Configuration loaded successfully",
            extra={
                "bigquery_project": config.bigquery_project,
                "bigquery_dataset": config.bigquery_dataset,
            },
        )

    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        sys.exit(1)

    # 2. Get bearer token (either from config or authenticate)
    if config.grow_bearer_token:
        logger.info("Using pre-generated bearer token from .env")
        bearer_token = config.grow_bearer_token
    else:
        try:
            logger.info("Authenticating with Grow API")
            bearer_token = get_bearer_token(
                config.grow_client_id,
                config.grow_client_secret,
            )
            logger.info("Authentication successful")

        except AuthenticationError as e:
            logger.error(f"Authentication failed: {str(e)}")
            sys.exit(1)

    # 3. Initialize clients
    logger.info("Initializing API and BigQuery clients")
    api_client = UsersAPIClient(bearer_token)
    bq_client = BigQueryClient(
        config.bigquery_project,
        config.bigquery_dataset,
    )

    try:
        # 4. Ensure BigQuery table exists
        logger.info(f"Ensuring BigQuery table exists: {TABLE_NAME}")
        bq_client.ensure_table_exists(TABLE_NAME, SCHEMA)

    except BigQueryError as e:
        logger.error(f"BigQuery table setup failed: {str(e)}")
        sys.exit(1)

    # 5. Fetch, transform, and load data
    logger.info("Starting data extraction and loading (active users only)")

    records_batch: List[Dict[str, Any]] = []
    total_fetched = 0
    total_transformed = 0
    total_loaded = 0
    transformation_errors = 0
    batch_size = 1000

    try:
        for record in api_client.fetch_users(archived=False):
            total_fetched += 1

            # Transform record
            try:
                transformed = transform_user(record)
                records_batch.append(transformed)
                total_transformed += 1

            except Exception as e:
                logger.warning(
                    f"Failed to transform record {record.get('_id', 'unknown')}: {str(e)}"
                )
                transformation_errors += 1
                continue

            # Load batch when it reaches batch_size
            if len(records_batch) >= batch_size:
                try:
                    bq_client.insert_rows(TABLE_NAME, records_batch)
                    total_loaded += len(records_batch)
                    logger.info(
                        f"Loaded batch to BigQuery",
                        extra={
                            "batch_size": len(records_batch),
                            "total_loaded": total_loaded,
                            "total_fetched": total_fetched,
                        },
                    )
                    records_batch = []

                except BigQueryError as e:
                    logger.error(f"Failed to load batch: {str(e)}")
                    records_batch = []

    except APIError as e:
        logger.error(f"API error during data fetch: {str(e)}")

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")

    # 6. Load any remaining records
    if records_batch:
        try:
            bq_client.insert_rows(TABLE_NAME, records_batch)
            total_loaded += len(records_batch)
            logger.info(
                f"Loaded final batch to BigQuery",
                extra={
                    "batch_size": len(records_batch),
                    "total_loaded": total_loaded,
                },
            )

        except BigQueryError as e:
            logger.error(f"Failed to load final batch: {str(e)}")

    # 7. Log summary
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()

    logger.info("=" * 60)
    logger.info("Pipeline completed successfully")
    logger.info("=" * 60)
    logger.info(
        "Pipeline summary",
        extra={
            "total_fetched": total_fetched,
            "total_transformed": total_transformed,
            "total_loaded": total_loaded,
            "transformation_errors": transformation_errors,
            "duration_seconds": round(duration, 2),
            "records_per_second": round(total_loaded / duration, 2) if duration > 0 else 0,
        },
    )

    # Verify final row count in BigQuery
    try:
        row_count = bq_client.get_table_row_count(TABLE_NAME)
        logger.info(
            f"BigQuery table now contains {row_count} total rows",
            extra={"table": TABLE_NAME, "row_count": row_count},
        )
    except Exception as e:
        logger.warning(f"Could not verify final row count: {str(e)}")


if __name__ == "__main__":
    main()
