"""Reload users from Grow API - excluding Level Data employees."""
import logging
import sys

from config import Config
from api_client import GrowAPIClient
from transformers_users import transform_user
from bigquery_client import BigQueryClient
from schema_users import SCHEMA, TABLE_NAME

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    """Load FirstLine users only (exclude @leveldata.com)."""
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

        # Fetch ALL users
        logger.info("Fetching ALL active users from API...")
        all_users = []
        skip = 0
        limit = 500

        while True:
            url = f"{api_client.BASE_URL}/users"
            params = {"archived": "false", "limit": limit, "skip": skip}

            response = api_client._make_request(url, params)
            users = response.get('data', [])

            if not users:
                break

            all_users.extend(users)
            skip += limit

            if len(users) < limit:
                break

        logger.info(f"Total users fetched from API: {len(all_users)}")

        # Filter out Level Data employees and non-FirstLine users
        firstline_users = []
        excluded_leveldata = 0
        excluded_other = 0

        for user in all_users:
            email = user.get('email', '')
            show_on_dashboards = user.get('showOnDashboards')

            # Exclude Level Data employees
            if '@leveldata.com' in email.lower():
                excluded_leveldata += 1
                continue

            # Exclude users with showOnDashboards=false (test accounts)
            if show_on_dashboards is False:
                excluded_other += 1
                continue

            # Exclude test/sample accounts
            if email.lower() in ['data@firstlineschools.org', 'sample.employee@firstlineschools.org', 'practice@firstline.com']:
                excluded_other += 1
                continue

            # Exclude non-FirstLine email domains
            if '@firstlineschools.org' not in email.lower() and '@firstline.com' not in email.lower():
                excluded_other += 1
                continue

            firstline_users.append(user)

        logger.info(f"Excluded {excluded_leveldata} Level Data employees")
        logger.info(f"Excluded {excluded_other} other non-FirstLine users")
        logger.info(f"FirstLine users to load: {len(firstline_users)}")

        # Transform users
        logger.info("Transforming users...")
        transformed = []
        for user in firstline_users:
            t = transform_user(user)
            if t:
                transformed.append(t)

        logger.info(f"Transformed {len(transformed)} users")

        # Truncate and reload
        logger.info("Truncating users table...")
        truncate_query = "DELETE FROM `confluence-point-consulting.grow.users` WHERE TRUE"
        from google.cloud import bigquery
        bq = bigquery.Client(project=config.bigquery_project)
        bq.query(truncate_query).result()

        # Load to BigQuery
        logger.info("Loading to BigQuery...")
        bq_client.insert_rows(TABLE_NAME, transformed)

        # Verify
        count = bq_client.get_table_row_count(TABLE_NAME)
        logger.info(f"✓ BigQuery table now contains {count} users")

        if count == 415:
            logger.info("✓ Perfect! Matches Grow's 415 active users count")

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
