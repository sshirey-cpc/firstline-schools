"""BigQuery schema definition for schools table."""
from google.cloud import bigquery


# Table name
TABLE_NAME = "schools"

# BigQuery schema for schools table
SCHEMA = [
    # Core school fields
    bigquery.SchemaField("school_id", "STRING", mode="REQUIRED", description="Unique school identifier (_id from API)"),
    bigquery.SchemaField("name", "STRING", mode="NULLABLE", description="School name"),
    bigquery.SchemaField("region", "STRING", mode="NULLABLE", description="School region/district"),
    bigquery.SchemaField("principal", "STRING", mode="NULLABLE", description="Principal name"),
    bigquery.SchemaField("phone", "STRING", mode="NULLABLE", description="School phone number"),
    bigquery.SchemaField("low_grade", "STRING", mode="NULLABLE", description="Lowest grade level"),
    bigquery.SchemaField("high_grade", "STRING", mode="NULLABLE", description="Highest grade level"),
    bigquery.SchemaField("address", "STRING", mode="NULLABLE", description="School address"),
    bigquery.SchemaField("city", "STRING", mode="NULLABLE", description="School city"),
    bigquery.SchemaField("state", "STRING", mode="NULLABLE", description="School state"),
    bigquery.SchemaField("zip", "STRING", mode="NULLABLE", description="School zip code"),

    # Admin arrays (stored as JSON strings for simplicity)
    bigquery.SchemaField("admins", "STRING", mode="REPEATED", description="Admin names"),
    bigquery.SchemaField("assistant_admins", "STRING", mode="REPEATED", description="Assistant admin names"),

    # Metadata
    bigquery.SchemaField("ingestion_timestamp", "TIMESTAMP", mode="REQUIRED", description="When this record was loaded into BigQuery"),
]


def get_table_id(project: str, dataset: str) -> str:
    """
    Get fully qualified BigQuery table ID.

    Args:
        project: BigQuery project ID
        dataset: BigQuery dataset ID

    Returns:
        Fully qualified table ID: project.dataset.table
    """
    return f"{project}.{dataset}.{TABLE_NAME}"
