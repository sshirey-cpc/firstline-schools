"""Main orchestrator for Grow API to BigQuery pipeline."""
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any
from pythonjsonlogger import jsonlogger

from config import Config
from auth import get_bearer_token, AuthenticationError
from api_client import GrowAPIClient, APIError
from bigquery_client import BigQueryClient, BigQueryError
from transformers import transform_assignment
from schema import SCHEMA, TABLE_NAME


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


def main() -> None:
    """
    Main pipeline orchestrator.

    Workflow:
    1. Load configuration from .env
    2. Authenticate with Grow API
    3. Initialize API and BigQuery clients
    4. Ensure BigQuery table exists
    5. Fetch records from API with pagination
    6. Transform each record
    7. Batch and load to BigQuery
    8. Log summary statistics
    """
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    start_time = datetime.utcnow()
    logger.info("=" * 60)
    logger.info("Starting Grow API to BigQuery pipeline")
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
    api_client = GrowAPIClient(bearer_token)
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
    logger.info("Starting data extraction and loading")

    records_batch: List[Dict[str, Any]] = []
    total_fetched = 0
    total_transformed = 0
    total_loaded = 0
    transformation_errors = 0
    batch_size = 1000

    try:
        for record in api_client.fetch_assignments():
            total_fetched += 1

            # Transform record
            try:
                transformed = transform_assignment(record)
                records_batch.append(transformed)
                total_transformed += 1

            except Exception as e:
                logger.warning(
                    f"Failed to transform record {record.get('id', 'unknown')}: {str(e)}"
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
                    # Continue with next batch, don't fail entire pipeline
                    records_batch = []

    except APIError as e:
        logger.error(f"API error during data fetch: {str(e)}")
        # Continue to load any remaining records

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
