"""Reload ALL users from Grow API to BigQuery - fetches with larger page size."""
import logging
import sys
from datetime import datetime

from config import Config
from api_client import GrowAPIClient
from transformers_users import transform_user
from bigquery_client import BigQueryClient
from schema_users import SCHEMA, TABLE_NAME

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    """Load all users with larger page size to ensure we get everyone."""
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = Config.load()

        # Get bearer token
        token = config.grow_bearer_token
        if not token:
            logger.error("No bearer token found")
            return 1

        # Initialize clients
        logger.info("Initializing clients...")
        api_client = GrowAPIClient(bearer_token=token)
        bq_client = BigQueryClient(config.bigquery_project, config.bigquery_dataset)

        # Fetch ALL users with larger page size
        logger.info("Fetching ALL active users from API...")
        all_users = []
        skip = 0
        limit = 500  # Use larger page size

        while True:
            url = f"{api_client.BASE_URL}/users"
            params = {"archived": "false", "limit": limit, "skip": skip}

            response = api_client._make_request(url, params)
            users = response.get('data', [])

            if not users:
                break

            all_users.extend(users)
            logger.info(f"  Fetched {len(all_users)} users so far...")
            skip += limit

            if len(users) < limit:
                break

        logger.info(f"Total users fetched: {len(all_users)}")

        # Transform users
        logger.info("Transforming users...")
        transformed = []
        for user in all_users:
            t = transform_user(user)
            if t:
                transformed.append(t)

        logger.info(f"Transformed {len(transformed)} users")

        # Load to BigQuery
        logger.info("Loading to BigQuery...")
        bq_client.insert_rows(TABLE_NAME, transformed)

        # Verify
        count = bq_client.get_table_row_count(TABLE_NAME)
        logger.info(f"✓ BigQuery table now contains {count} users")

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
