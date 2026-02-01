"""BigQuery schema definition for assignments table."""
from google.cloud import bigquery


# Table name
TABLE_NAME = "assignments"

# BigQuery schema for assignments table
SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED", description="Unique assignment identifier"),
    bigquery.SchemaField("type", "STRING", mode="NULLABLE", description="Assignment type (e.g., actionStep, observation, etc.)"),
    bigquery.SchemaField("title", "STRING", mode="NULLABLE", description="Assignment title"),
    bigquery.SchemaField("description", "STRING", mode="NULLABLE", description="Assignment description (HTML stripped)"),
    bigquery.SchemaField("status", "STRING", mode="NULLABLE", description="Current status of the assignment"),
    bigquery.SchemaField("due_date", "TIMESTAMP", mode="NULLABLE", description="Due date for the action step"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE", description="Creation timestamp"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE", description="Last update timestamp"),

    # Creator fields (flattened)
    bigquery.SchemaField("creator_id", "STRING", mode="NULLABLE", description="ID of the user who created this assignment"),
    bigquery.SchemaField("creator_name", "STRING", mode="NULLABLE", description="Name of the creator"),
    bigquery.SchemaField("creator_email", "STRING", mode="NULLABLE", description="Email of the creator"),

    # Assignee/User fields (flattened)
    bigquery.SchemaField("user_id", "STRING", mode="NULLABLE", description="ID of the assigned user"),
    bigquery.SchemaField("user_name", "STRING", mode="NULLABLE", description="Name of the assigned user"),
    bigquery.SchemaField("user_email", "STRING", mode="NULLABLE", description="Email of the assigned user"),

    # Progress fields (flattened)
    bigquery.SchemaField("progress_percentage", "FLOAT", mode="NULLABLE", description="Completion percentage"),
    bigquery.SchemaField("progress_completed_steps", "INTEGER", mode="NULLABLE", description="Number of completed steps"),
    bigquery.SchemaField("progress_total_steps", "INTEGER", mode="NULLABLE", description="Total number of steps"),

    # Tags (as repeated field/array)
    bigquery.SchemaField("tags", "STRING", mode="REPEATED", description="Tags associated with this assignment"),

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
