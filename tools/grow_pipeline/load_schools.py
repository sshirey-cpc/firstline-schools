"""Load schools data from Grow API to BigQuery."""
import logging
import sys
from typing import List, Dict, Any

from config import Config
from auth import get_bearer_token
from api_client import GrowAPIClient
from transformers_schools import transform_school
from bigquery_client import BigQueryClient
from schema_schools import SCHEMA, TABLE_NAME, get_table_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def main():
    """Main ETL pipeline for schools data."""
    try:
        # Step 1: Load configuration
        logger.info("Loading configuration...")
        config = Config.load()

        # Step 2: Get bearer token
        logger.info("Getting bearer token...")
        token = config.grow_bearer_token
        if not token:
            logger.info("No pre-generated token found, authenticating...")
            token = get_bearer_token(config.grow_client_id, config.grow_client_secret)
        if not token:
            logger.error("Failed to obtain bearer token")
            return 1

        # Step 3: Initialize clients
        logger.info("Initializing API and BigQuery clients...")
        api_client = GrowAPIClient(bearer_token=token)
        bq_client = BigQueryClient(
            config.bigquery_project,
            config.bigquery_dataset
        )

        # Step 4: Ensure BigQuery table exists
        table_id = get_table_id(config.bigquery_project, config.bigquery_dataset)
        logger.info(f"Ensuring BigQuery table exists: {table_id}")
        bq_client.ensure_table_exists(TABLE_NAME, SCHEMA)

        # Step 5: Fetch schools from API
        logger.info("Fetching schools from Grow API...")
        url = f"{api_client.BASE_URL}/schools"
        params = {"archived": "false"}
        response = api_client._make_request(url, params)

        # Extract schools from response
        if isinstance(response, list):
            raw_schools = response
        else:
            raw_schools = response.get('data', [])

        logger.info(f"Fetched {len(raw_schools)} schools from API")

        # Step 6: Transform schools
        logger.info("Transforming schools data...")
        transformed_schools = []
        for school in raw_schools:
            transformed = transform_school(school)
            if transformed:
                transformed_schools.append(transformed)

        logger.info(f"Successfully transformed {len(transformed_schools)} schools")

        # Step 7: Load to BigQuery (in batches)
        logger.info("Loading schools to BigQuery...")
        batch_size = 1000
        total_loaded = 0

        for i in range(0, len(transformed_schools), batch_size):
            batch = transformed_schools[i:i + batch_size]
            bq_client.insert_rows(TABLE_NAME, batch)
            total_loaded += len(batch)
            logger.info(f"Loaded batch: {total_loaded}/{len(transformed_schools)} schools")

        # Step 8: Verify
        row_count = bq_client.get_table_row_count(TABLE_NAME)
        logger.info(f"BigQuery table '{TABLE_NAME}' now contains {row_count} rows")

        logger.info("✓ Schools pipeline completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
