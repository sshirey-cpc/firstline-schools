"""
Setup script to load position control data into BigQuery.
Run this once to create the table and load initial data.
"""

import json
import os
import time
import uuid
from datetime import datetime
from google.cloud import bigquery
from config import PROJECT_ID, DATASET_ID, POSITION_TABLE

HISTORY_TABLE = "position_history"


def load_positions_to_bigquery(json_file_path: str):
    """Load position data from JSON file into BigQuery."""

    client = bigquery.Client(project=PROJECT_ID)
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}"
    history_table_id = f"{PROJECT_ID}.{DATASET_ID}.{HISTORY_TABLE}"

    # Define schema with ID and audit fields
    schema = [
        bigquery.SchemaField("position_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("school", "STRING"),
        bigquery.SchemaField("job_category", "STRING"),
        bigquery.SchemaField("job_title", "STRING"),
        bigquery.SchemaField("subject", "STRING"),
        bigquery.SchemaField("grade_level", "STRING"),
        bigquery.SchemaField("staffing_matrix", "STRING"),
        bigquery.SchemaField("current_status", "STRING"),
        bigquery.SchemaField("first_name", "STRING"),
        bigquery.SchemaField("last_name", "STRING"),
        bigquery.SchemaField("employee_25_26", "STRING"),
        bigquery.SchemaField("email_address", "STRING"),
        bigquery.SchemaField("employee_number", "STRING"),
        bigquery.SchemaField("validation", "STRING"),
        bigquery.SchemaField("employee_26_27", "STRING"),
        bigquery.SchemaField("status_26_27", "STRING"),
        bigquery.SchemaField("itr_response", "STRING"),
        bigquery.SchemaField("notes", "STRING"),
        bigquery.SchemaField("candidate_name", "STRING"),
        bigquery.SchemaField("start_year", "STRING"),
        bigquery.SchemaField("end_year", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
        bigquery.SchemaField("updated_by", "STRING"),
    ]

    # History table schema
    history_schema = [
        bigquery.SchemaField("history_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("position_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("action", "STRING"),  # CREATE, UPDATE, DELETE
        bigquery.SchemaField("field_changed", "STRING"),
        bigquery.SchemaField("old_value", "STRING"),
        bigquery.SchemaField("new_value", "STRING"),
        bigquery.SchemaField("changed_by", "STRING"),
        bigquery.SchemaField("changed_at", "TIMESTAMP"),
    ]

    # Load JSON data
    with open(json_file_path, 'r') as f:
        raw_data = json.load(f)

    now = datetime.utcnow().isoformat()

    # Transform to match schema
    rows = []
    for i, item in enumerate(raw_data):
        # Convert FLS departments to "Network"
        school = item.get("School", "")
        if school.startswith("FLS"):
            school = "Network"

        row = {
            "position_id": str(uuid.uuid4()),
            "school": school,
            "job_category": item.get("Job Category", ""),
            "job_title": item.get("Job Title", ""),
            "subject": item.get("Subject", ""),
            "grade_level": item.get("Grade Level", ""),
            "staffing_matrix": item.get("Staffing Matrix", ""),
            "current_status": item.get("Current Status", ""),
            "first_name": item.get("First Name", ""),
            "last_name": item.get("Last Name", ""),
            "employee_25_26": item.get("25-26 Employee", ""),
            "email_address": item.get("Email Address", ""),
            "employee_number": str(item.get("Employee Number", "")),
            "validation": item.get("Validation", ""),
            "employee_26_27": item.get("26-27 Employee", ""),
            "status_26_27": item.get("26-27 Status", ""),
            "itr_response": item.get("ITR Response", ""),
            "notes": "",
            "candidate_name": "",
            "start_year": "25-26",
            "end_year": None,
            "created_at": now,
            "updated_at": now,
            "updated_by": "system",
        }
        rows.append(row)

    # Delete and recreate positions table
    try:
        client.delete_table(table_id)
        print(f"Deleted existing table {table_id}")
    except Exception:
        pass

    table = bigquery.Table(table_id, schema=schema)
    table = client.create_table(table)
    print(f"Created table {table_id}")

    # Create history table if not exists
    try:
        client.get_table(history_table_id)
        print(f"History table {history_table_id} already exists")
    except Exception:
        history_table = bigquery.Table(history_table_id, schema=history_schema)
        client.create_table(history_table)
        print(f"Created history table {history_table_id}")

    # Wait for table to be available
    time.sleep(2)

    # Insert rows
    errors = client.insert_rows_json(table_id, rows)

    if errors:
        print(f"Errors inserting rows: {errors}")
        return False

    print(f"Successfully loaded {len(rows)} positions into {table_id}")
    return True


def add_candidate_name_column():
    """Add candidate_name column to existing position_control table."""
    client = bigquery.Client(project=PROJECT_ID)
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}"

    try:
        table = client.get_table(table_id)
        original_schema = list(table.schema)

        # Check if column already exists
        if any(field.name == "candidate_name" for field in original_schema):
            print("candidate_name column already exists")
            return True

        # Add new column
        new_schema = original_schema + [bigquery.SchemaField("candidate_name", "STRING")]
        table.schema = new_schema
        client.update_table(table, ["schema"])
        print(f"Added candidate_name column to {table_id}")
        return True

    except Exception as e:
        print(f"Error adding column: {e}")
        return False


def add_year_range_columns():
    """
    Add start_year and end_year columns to position_control table.
    This enables tracking which school years a position applies to.
    - start_year: When the position was created (e.g., "25-26")
    - end_year: When the position ends (NULL = ongoing)
    """
    client = bigquery.Client(project=PROJECT_ID)
    table_id = f"{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}"

    try:
        table = client.get_table(table_id)
        original_schema = list(table.schema)

        # Check which columns need to be added
        existing_fields = {field.name for field in original_schema}
        new_fields = []

        if "start_year" not in existing_fields:
            new_fields.append(bigquery.SchemaField("start_year", "STRING"))
            print("Will add start_year column")
        else:
            print("start_year column already exists")

        if "end_year" not in existing_fields:
            new_fields.append(bigquery.SchemaField("end_year", "STRING"))
            print("Will add end_year column")
        else:
            print("end_year column already exists")

        if not new_fields:
            print("All year columns already exist")
            return True

        # Add new columns
        new_schema = original_schema + new_fields
        table.schema = new_schema
        client.update_table(table, ["schema"])
        print(f"Added year columns to {table_id}")

        # Set default values for existing positions
        # All existing positions started in 25-26 and are ongoing (end_year = NULL)
        update_query = f"""
            UPDATE `{table_id}`
            SET start_year = '25-26'
            WHERE start_year IS NULL
        """
        client.query(update_query).result()
        print("Set default start_year='25-26' for existing positions")

        return True

    except Exception as e:
        print(f"Error adding year columns: {e}")
        return False


if __name__ == "__main__":
    # Look for staffing_data.json in parent directory or current directory
    json_paths = [
        "../bigquery_dashboards/staffing_data.json",
        "staffing_data.json",
        "../staffing_data.json",
    ]

    json_file = None
    for path in json_paths:
        if os.path.exists(path):
            json_file = path
            break

    if not json_file:
        print("Error: Could not find staffing_data.json")
        print("Please provide the path to the JSON file.")
        exit(1)

    print(f"Loading data from: {json_file}")
    success = load_positions_to_bigquery(json_file)

    if success:
        print("\nSetup complete! You can now run the Position Control app.")
    else:
        print("\nSetup failed. Please check the errors above.")
