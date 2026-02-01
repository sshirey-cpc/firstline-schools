"""BigQuery schema definition for users table."""
from google.cloud import bigquery


# Table name
TABLE_NAME = "users"

# BigQuery schema for users table
SCHEMA = [
    # Core user fields
    bigquery.SchemaField("user_id", "STRING", mode="REQUIRED", description="Unique user identifier (_id from API)"),
    bigquery.SchemaField("email", "STRING", mode="NULLABLE", description="User email address"),
    bigquery.SchemaField("first_name", "STRING", mode="NULLABLE", description="First name"),
    bigquery.SchemaField("last_name", "STRING", mode="NULLABLE", description="Last name"),
    bigquery.SchemaField("full_name", "STRING", mode="NULLABLE", description="Full name"),
    bigquery.SchemaField("internal_id", "STRING", mode="NULLABLE", description="Internal user ID"),

    # Timestamps
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE", description="Account creation timestamp"),
    bigquery.SchemaField("last_activity", "TIMESTAMP", mode="NULLABLE", description="Last activity timestamp"),
    bigquery.SchemaField("last_modified", "TIMESTAMP", mode="NULLABLE", description="Last modification timestamp"),
    bigquery.SchemaField("archived_at", "TIMESTAMP", mode="NULLABLE", description="Archive timestamp"),

    # Status flags
    bigquery.SchemaField("inactive", "BOOLEAN", mode="NULLABLE", description="Is user inactive"),
    bigquery.SchemaField("locked", "BOOLEAN", mode="NULLABLE", description="Is user locked"),
    bigquery.SchemaField("readonly", "BOOLEAN", mode="NULLABLE", description="Is user readonly"),
    bigquery.SchemaField("show_on_dashboards", "BOOLEAN", mode="NULLABLE", description="Show user on dashboards"),
    bigquery.SchemaField("non_instructional", "BOOLEAN", mode="NULLABLE", description="Is non-instructional staff"),
    bigquery.SchemaField("video_license", "BOOLEAN", mode="NULLABLE", description="Has video license"),

    # Relationships
    bigquery.SchemaField("coach_id", "STRING", mode="NULLABLE", description="ID of assigned coach"),
    bigquery.SchemaField("evaluator_id", "STRING", mode="NULLABLE", description="ID of assigned evaluator"),

    # Default information (flattened)
    bigquery.SchemaField("default_school_id", "STRING", mode="NULLABLE", description="Default school ID"),
    bigquery.SchemaField("default_grade_level_id", "STRING", mode="NULLABLE", description="Default grade level ID"),
    bigquery.SchemaField("default_course_id", "STRING", mode="NULLABLE", description="Default course ID"),

    # User type (flattened)
    bigquery.SchemaField("usertype_id", "STRING", mode="NULLABLE", description="User type ID"),
    bigquery.SchemaField("usertype_name", "STRING", mode="NULLABLE", description="User type name"),

    # Districts and roles (arrays)
    bigquery.SchemaField("districts", "STRING", mode="REPEATED", description="District IDs"),
    bigquery.SchemaField("roles", "STRING", mode="REPEATED", description="Role names"),

    # User tags
    bigquery.SchemaField("usertag1", "STRING", mode="NULLABLE", description="User tag 1"),
    bigquery.SchemaField("usertag2", "STRING", mode="NULLABLE", description="User tag 2"),
    bigquery.SchemaField("usertag3", "STRING", mode="NULLABLE", description="User tag 3"),
    bigquery.SchemaField("usertag4", "STRING", mode="NULLABLE", description="User tag 4"),
    bigquery.SchemaField("usertag5", "STRING", mode="NULLABLE", description="User tag 5"),
    bigquery.SchemaField("usertag6", "STRING", mode="NULLABLE", description="User tag 6"),
    bigquery.SchemaField("usertag7", "STRING", mode="NULLABLE", description="User tag 7"),
    bigquery.SchemaField("usertag8", "STRING", mode="NULLABLE", description="User tag 8"),

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
