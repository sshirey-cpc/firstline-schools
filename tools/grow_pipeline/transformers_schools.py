"""Transformers for schools data from Grow API."""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def transform_school(raw_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Transform a raw school record from Grow API to BigQuery format.

    Args:
        raw_record: Raw school record from the API

    Returns:
        Transformed record ready for BigQuery, or None if transformation fails
    """
    try:
        # Extract admin names
        admins = []
        if raw_record.get('admins'):
            admins = [admin.get('name', '') for admin in raw_record['admins'] if admin.get('name')]

        # Extract assistant admin names
        assistant_admins = []
        if raw_record.get('assistantAdmins'):
            assistant_admins = [admin.get('name', '') for admin in raw_record['assistantAdmins'] if admin.get('name')]

        transformed = {
            'school_id': raw_record.get('_id'),
            'name': raw_record.get('name'),
            'region': raw_record.get('region'),
            'principal': raw_record.get('principal'),
            'phone': raw_record.get('phone'),
            'low_grade': raw_record.get('lowGrade'),
            'high_grade': raw_record.get('highGrade'),
            'address': raw_record.get('address'),
            'city': raw_record.get('city'),
            'state': raw_record.get('state'),
            'zip': raw_record.get('zip'),
            'admins': admins,
            'assistant_admins': assistant_admins,
            'ingestion_timestamp': datetime.utcnow().isoformat() + 'Z',
        }

        return transformed

    except Exception as e:
        logger.error(f"Error transforming school record: {e}")
        logger.error(f"Problematic record: {raw_record}")
        # Return minimal record to avoid data loss
        return {
            'school_id': raw_record.get('_id'),
            'name': raw_record.get('name'),
            'region': None,
            'principal': None,
            'phone': None,
            'low_grade': None,
            'high_grade': None,
            'address': None,
            'city': None,
            'state': None,
            'zip': None,
            'admins': [],
            'assistant_admins': [],
            'ingestion_timestamp': datetime.utcnow().isoformat() + 'Z',
        }
