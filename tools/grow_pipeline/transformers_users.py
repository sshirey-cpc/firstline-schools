"""Data transformation utilities for Grow API users data."""
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


def parse_timestamp(timestamp_str: str) -> str:
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
        if isinstance(timestamp_str, str):
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return dt.isoformat()
        return None
    except (ValueError, AttributeError) as e:
        logger.warning(f"Failed to parse timestamp '{timestamp_str}': {str(e)}")
        return None


def transform_user(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a raw user record from API to BigQuery schema.

    Args:
        record: Raw user record from API

    Returns:
        Transformed record matching BigQuery schema
    """
    try:
        transformed = {}

        # Core user fields
        transformed["user_id"] = record.get("_id")
        transformed["email"] = record.get("email")
        transformed["first_name"] = record.get("first")
        transformed["last_name"] = record.get("last")
        transformed["full_name"] = record.get("name")
        transformed["internal_id"] = record.get("internalId")

        # Timestamps
        transformed["created_at"] = parse_timestamp(record.get("created"))
        transformed["last_activity"] = parse_timestamp(record.get("lastActivity"))
        transformed["last_modified"] = parse_timestamp(record.get("lastModified"))
        transformed["archived_at"] = parse_timestamp(record.get("archivedAt"))

        # Status flags
        transformed["inactive"] = record.get("inactive")
        transformed["locked"] = record.get("locked")
        transformed["readonly"] = record.get("readonly")
        transformed["show_on_dashboards"] = record.get("showOnDashboards")
        transformed["non_instructional"] = record.get("nonInstructional")
        transformed["video_license"] = record.get("videoLicense")

        # Relationships
        transformed["coach_id"] = record.get("coach")
        transformed["evaluator_id"] = record.get("evaluator")

        # Default information (flatten nested object)
        default_info = record.get("defaultInformation", {})
        if default_info and isinstance(default_info, dict):
            transformed["default_school_id"] = default_info.get("school")
            transformed["default_grade_level_id"] = default_info.get("gradeLevel")
            transformed["default_course_id"] = default_info.get("course")
        else:
            transformed["default_school_id"] = None
            transformed["default_grade_level_id"] = None
            transformed["default_course_id"] = None

        # User type (flatten nested object)
        usertype = record.get("usertype", {})
        if usertype and isinstance(usertype, dict):
            transformed["usertype_id"] = usertype.get("_id")
            transformed["usertype_name"] = usertype.get("name")
        else:
            transformed["usertype_id"] = None
            transformed["usertype_name"] = None

        # Districts (array)
        districts = record.get("districts", [])
        if isinstance(districts, list):
            transformed["districts"] = [str(d) for d in districts if d]
        else:
            transformed["districts"] = []

        # Roles (extract names from array of objects)
        roles = record.get("roles", [])
        if isinstance(roles, list):
            role_names = []
            for role in roles:
                if isinstance(role, dict) and "name" in role:
                    role_names.append(role["name"])
                elif isinstance(role, str):
                    role_names.append(role)
            transformed["roles"] = role_names
        else:
            transformed["roles"] = []

        # User tags
        transformed["usertag1"] = record.get("usertag1")
        transformed["usertag2"] = record.get("usertag2")
        transformed["usertag3"] = record.get("usertag3")
        transformed["usertag4"] = record.get("usertag4")
        transformed["usertag5"] = record.get("usertag5")
        transformed["usertag6"] = record.get("usertag6")
        transformed["usertag7"] = record.get("usertag7")
        transformed["usertag8"] = record.get("usertag8")

        # Add ingestion timestamp
        transformed["ingestion_timestamp"] = datetime.utcnow().isoformat()

        return transformed

    except Exception as e:
        logger.error(f"Error transforming user record {record.get('_id', 'unknown')}: {str(e)}")
        # Return a minimal record to avoid losing data
        return {
            "user_id": record.get("_id", "unknown"),
            "email": record.get("email"),
            "first_name": None,
            "last_name": None,
            "full_name": None,
            "internal_id": None,
            "created_at": None,
            "last_activity": None,
            "last_modified": None,
            "archived_at": None,
            "inactive": None,
            "locked": None,
            "readonly": None,
            "show_on_dashboards": None,
            "non_instructional": None,
            "video_license": None,
            "coach_id": None,
            "evaluator_id": None,
            "default_school_id": None,
            "default_grade_level_id": None,
            "default_course_id": None,
            "usertype_id": None,
            "usertype_name": None,
            "districts": [],
            "roles": [],
            "usertag1": None,
            "usertag2": None,
            "usertag3": None,
            "usertag4": None,
            "usertag5": None,
            "usertag6": None,
            "usertag7": None,
            "usertag8": None,
            "ingestion_timestamp": datetime.utcnow().isoformat(),
        }
