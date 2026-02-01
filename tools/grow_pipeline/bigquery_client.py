"""BigQuery client for loading data."""
import logging
from typing import List, Dict, Any
from google.cloud import bigquery
from google.api_core import exceptions

logger = logging.getLogger(__name__)


class BigQueryError(Exception):
    """Raised when BigQuery operation fails."""
    pass


class BigQueryClient:
    """Client for BigQuery operations."""

    def __init__(self, project_id: str, dataset_id: str):
        """
        Initialize BigQuery client.

        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset ID
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.client = bigquery.Client(project=project_id)
        self.dataset_ref = self.client.dataset(dataset_id)

    def ensure_table_exists(
        self,
        table_name: str,
        schema: List[bigquery.SchemaField],
    ) -> None:
        """
        Ensure BigQuery table exists, create if it doesn't.

        Args:
            table_name: Name of the table
            schema: BigQuery schema definition

        Raises:
            BigQueryError: If table creation fails
        """
        table_id = f"{self.project_id}.{self.dataset_id}.{table_name}"

        try:
            # Check if table exists
            self.client.get_table(table_id)
            logger.info(f"Table {table_id} already exists")

        except exceptions.NotFound:
            # Table doesn't exist, create it
            logger.info(f"Table {table_id} not found, creating...")

            table = bigquery.Table(table_id, schema=schema)

            # Optional: Add table description
            table.description = "Action steps from Grow API"

            try:
                table = self.client.create_table(table)
                logger.info(f"Successfully created table {table_id}")

            except Exception as e:
                logger.error(f"Failed to create table: {str(e)}")
                raise BigQueryError(f"Failed to create table {table_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Error checking table existence: {str(e)}")
            raise BigQueryError(f"Error checking table {table_id}: {str(e)}")

    def insert_rows(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
    ) -> None:
        """
        Insert rows into BigQuery table using load job.

        Args:
            table_name: Name of the table
            records: List of records to insert

        Raises:
            BigQueryError: If insert fails
        """
        if not records:
            logger.warning("No records to insert")
            return

        table_id = f"{self.project_id}.{self.dataset_id}.{table_name}"

        try:
            # Get existing table schema
            table = self.client.get_table(table_id)

            # Configure load job with explicit schema
            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
                schema=table.schema,  # Use table's existing schema
                autodetect=False,
            )

            # Start load job
            logger.info(f"Inserting {len(records)} records into {table_id}")
            load_job = self.client.load_table_from_json(
                records,
                table_id,
                job_config=job_config,
            )

            # Wait for job to complete
            load_job.result()

            logger.info(
                f"Successfully loaded {len(records)} records into {table_id}. "
                f"Total rows in table: {load_job.output_rows}"
            )

        except exceptions.BadRequest as e:
            logger.error(f"Bad request error: {str(e)}")
            # Log the first record to help debug schema issues
            if records:
                logger.error(f"Sample record: {records[0]}")
            raise BigQueryError(f"Failed to insert records: {str(e)}")

        except Exception as e:
            logger.error(f"Failed to insert records: {str(e)}")
            raise BigQueryError(f"Failed to insert records into {table_id}: {str(e)}")

    def get_table_row_count(self, table_name: str) -> int:
        """
        Get the number of rows in a table.

        Args:
            table_name: Name of the table

        Returns:
            Number of rows in the table
        """
        table_id = f"{self.project_id}.{self.dataset_id}.{table_name}"

        try:
            table = self.client.get_table(table_id)
            return table.num_rows
        except Exception as e:
            logger.error(f"Failed to get row count: {str(e)}")
            return 0
