"""Data transformation utilities for Grow API data."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def strip_html(html_text: Optional[str]) -> Optional[str]:
    """
    Strip HTML tags from text and return plain text.

    Args:
        html_text: Text potentially containing HTML

    Returns:
        Plain text with HTML tags removed, or None if input is None/empty
    """
    if not html_text:
        return None

    try:
        soup = BeautifulSoup(html_text, "lxml")
        text = soup.get_text(strip=True)
        return text if text else None
    except Exception as e:
        logger.warning(f"Failed to strip HTML, returning original: {str(e)}")
        return html_text


def parse_timestamp(timestamp_str: Optional[str]) -> Optional[str]:
    """
    Parse and validate timestamp string.

    Args:
        timestamp_str: ISO 8601 timestamp string

    Returns:
        ISO 8601 timestamp string in UTC, or None if invalid
    """
    if not timestamp_str:
        return None

    try:
        # Try parsing various timestamp formats
        # ISO 8601 formats: "2026-01-15T10:30:00Z" or "2026-01-15T10:30:00.123Z"
        if isinstance(timestamp_str, str):
            # If already in ISO format, validate it parses correctly
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return dt.isoformat()
        return None
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse timestamp '{timestamp_str}': {str(e)}")
        return None


def flatten_nested_object(
    record: Dict[str, Any],
    nested_key: str,
    field_mappings: Dict[str, str],
) -> Dict[str, Any]:
    """
    Flatten a nested object into top-level fields.

    Args:
        record: The record containing the nested object
        nested_key: Key of the nested object (e.g., 'creator', 'user')
        field_mappings: Mapping of nested field names to flattened field names
                       e.g., {'id': 'creator_id', 'name': 'creator_name'}

    Returns:
        Dictionary with flattened fields
    """
    flattened = {}
    nested_obj = record.get(nested_key)

    if nested_obj and isinstance(nested_obj, dict):
        for nested_field, flat_field in field_mappings.items():
            flattened[flat_field] = nested_obj.get(nested_field)
    else:
        # Set all fields to None if nested object doesn't exist
        for flat_field in field_mappings.values():
            flattened[flat_field] = None

    return flattened


def transform_assignment(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a raw assignment record from API to BigQuery schema.

    Args:
        record: Raw assignment record from API

    Returns:
        Transformed record matching BigQuery schema
    """
    try:
        transformed = {}

        # Basic fields - API uses _id and name, not id and title
        transformed["id"] = record.get("_id")
        transformed["type"] = record.get("type")

        # Name field often contains HTML, extract both title and description from it
        name = record.get("name")
        transformed["title"] = strip_html(name) if name else None
        transformed["description"] = strip_html(name) if name else None
        transformed["status"] = record.get("status")

        # Parse timestamps - API uses 'created' and 'lastModified'
        transformed["due_date"] = parse_timestamp(record.get("dueDate") or record.get("due_date"))
        transformed["created_at"] = parse_timestamp(record.get("created"))
        transformed["updated_at"] = parse_timestamp(record.get("lastModified"))

        # Flatten creator object
        creator_fields = flatten_nested_object(
            record,
            "creator",
            {
                "id": "creator_id",
                "name": "creator_name",
                "email": "creator_email",
            },
        )
        transformed.update(creator_fields)

        # Flatten user/assignee object
        user_fields = flatten_nested_object(
            record,
            "user",
            {
                "id": "user_id",
                "name": "user_name",
                "email": "user_email",
            },
        )
        transformed.update(user_fields)

        # Flatten progress object - API uses 'percent' not 'percentage'
        progress = record.get("progress")
        if progress and isinstance(progress, dict):
            transformed["progress_percentage"] = progress.get("percent")
            transformed["progress_completed_steps"] = progress.get("completedSteps") or progress.get("completed_steps")
            transformed["progress_total_steps"] = progress.get("totalSteps") or progress.get("total_steps")
        else:
            transformed["progress_percentage"] = None
            transformed["progress_completed_steps"] = None
            transformed["progress_total_steps"] = None

        # Handle tags - API returns array of objects with 'name' field
        tags = record.get("tags")
        if isinstance(tags, list):
            tag_names = []
            for tag in tags:
                if isinstance(tag, dict) and "name" in tag:
                    tag_names.append(tag["name"])
                elif isinstance(tag, str):
                    tag_names.append(tag)
            transformed["tags"] = tag_names
        elif isinstance(tags, str):
            transformed["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            transformed["tags"] = []

        # Add ingestion timestamp
        transformed["ingestion_timestamp"] = datetime.utcnow().isoformat()

        return transformed

    except Exception as e:
        logger.error(f"Error transforming record {record.get('id', 'unknown')}: {str(e)}")
        # Return a minimal record to avoid losing data
        return {
            "id": record.get("id", "unknown"),
            "type": record.get("type"),
            "title": None,
            "description": None,
            "status": None,
            "due_date": None,
            "created_at": None,
            "updated_at": None,
            "creator_id": None,
            "creator_name": None,
            "creator_email": None,
            "user_id": None,
            "user_name": None,
            "user_email": None,
            "progress_percentage": None,
            "progress_completed_steps": None,
            "progress_total_steps": None,
            "tags": [],
            "ingestion_timestamp": datetime.utcnow().isoformat(),
        }
