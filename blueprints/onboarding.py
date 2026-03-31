"""
Onboarding Form — Admin Dashboard Blueprint
Ported from standalone onboarding-form/app.py
"""

import os
import logging
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, session
from google.cloud import bigquery

from config import (
    PROJECT_ID, ONBOARDING_DATASET_ID, ONBOARDING_TABLE_ID,
)
from extensions import bq_client
from auth import get_onboarding_access, get_onboarding_permissions

logger = logging.getLogger(__name__)

bp = Blueprint('onboarding', __name__)

# ── Helpers ──

def get_full_table_id():
    return f"{PROJECT_ID}.{ONBOARDING_DATASET_ID}.{ONBOARDING_TABLE_ID}"


def onboarding_admin_required(f):
    """Require login + Onboarding role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        email = session['user'].get('email', '').lower()
        if not get_onboarding_access(email):
            return jsonify({'error': 'Onboarding access required'}), 403
        return f(*args, **kwargs)
    return decorated


def row_to_dict(row):
    return {
        'submission_id': row.submission_id,
        'submitted_at': row.submitted_at.isoformat() if row.submitted_at else '',
        'email': row.email or '',
        'first_name': row.first_name or '',
        'last_name': row.last_name or '',
        'preferred_name': row.preferred_name or '',
        'school_location': row.school_location or '',
        'tshirt_size': row.tshirt_size or '',
        'dietary_needs': row.dietary_needs or '',
        'food_allergies': row.food_allergies or '',
        'reading_certification': row.reading_certification or '',
        'numeracy_coursework': row.numeracy_coursework or '',
        'ada_accommodation': row.ada_accommodation or '',
        'onboarding_status': row.onboarding_status or '',
        'start_date': row.start_date.isoformat() if row.start_date else '',
        'position_title': row.position_title or '',
        'badge_printed': row.badge_printed or '',
        'equipment_issued': row.equipment_issued or '',
        'orientation_complete': row.orientation_complete or '',
        'admin_notes': row.admin_notes or '',
        'updated_at': row.updated_at.isoformat() if row.updated_at else '',
        'updated_by': row.updated_by or '',
        'is_archived': bool(getattr(row, 'is_archived', False) or False),
    }


def read_all_submissions():
    try:
        query = f"SELECT * FROM `{get_full_table_id()}` ORDER BY submitted_at DESC"
        return [row_to_dict(r) for r in bq_client.query(query).result()]
    except Exception as e:
        logger.error(f"Error reading onboarding submissions: {e}")
        return []


def update_submission(submission_id, updates):
    try:
        clauses, params = [], [bigquery.ScalarQueryParameter("submission_id", "STRING", submission_id)]
        for field, value in updates.items():
            p = f"param_{field}"
            if field == 'start_date':
                if value:
                    clauses.append(f"{field} = @{p}")
                    params.append(bigquery.ScalarQueryParameter(p, "DATE", value))
                else:
                    clauses.append(f"{field} = NULL")
            elif field in ('updated_at', 'submitted_at'):
                clauses.append(f"{field} = @{p}")
                params.append(bigquery.ScalarQueryParameter(p, "TIMESTAMP", datetime.fromisoformat(value)))
            elif field == 'is_archived':
                clauses.append(f"{field} = @{p}")
                params.append(bigquery.ScalarQueryParameter(p, "BOOL", bool(value)))
            else:
                clauses.append(f"{field} = @{p}")
                params.append(bigquery.ScalarQueryParameter(p, "STRING", str(value)))
        if not clauses:
            return True
        query = f"UPDATE `{get_full_table_id()}` SET {', '.join(clauses)} WHERE submission_id = @submission_id"
        bq_client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return True
    except Exception as e:
        logger.error(f"Error updating onboarding submission: {e}")
        return False


# ── Routes ──

@bp.route('/onboarding-dashboard')
def dashboard():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from app import serve_html
    return serve_html(os.path.join(root, 'onboarding-dashboard.html'))


@bp.route('/api/onboarding/admin/submissions', methods=['GET'])
@onboarding_admin_required
def get_all_submissions():
    return jsonify({'submissions': read_all_submissions()})


@bp.route('/api/onboarding/admin/submissions/<submission_id>', methods=['PATCH'])
@onboarding_admin_required
def update_submission_status(submission_id):
    try:
        data = request.json
        user = session.get('user', {})
        email = user.get('email', '').lower()
        perms = get_onboarding_permissions(email)

        if not perms or not perms['can_edit']:
            return jsonify({'error': 'You do not have permission to edit submissions'}), 403

        updates = {}

        for field in ['onboarding_status', 'position_title', 'badge_printed',
                      'equipment_issued', 'orientation_complete', 'admin_notes']:
            if field in data:
                updates[field] = data[field]

        if 'start_date' in data:
            updates['start_date'] = data['start_date']

        updates['updated_at'] = datetime.now().isoformat()
        updates['updated_by'] = user.get('email', 'Unknown')

        if update_submission(submission_id, updates):
            return jsonify({'success': True})
        return jsonify({'error': 'Submission not found'}), 404
    except Exception as e:
        logger.error(f"Error updating onboarding submission: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/onboarding/admin/submissions/<submission_id>', methods=['DELETE'])
@onboarding_admin_required
def delete_submission(submission_id):
    try:
        email = session.get('user', {}).get('email', '').lower()
        perms = get_onboarding_permissions(email)
        if not perms or not perms['can_delete']:
            return jsonify({'error': 'Only super admins can delete submissions'}), 403

        query = f"DELETE FROM `{get_full_table_id()}` WHERE submission_id = @submission_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("submission_id", "STRING", submission_id)]
        )
        bq_client.query(query, job_config=cfg).result()
        logger.info(f"Deleted onboarding submission {submission_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting onboarding submission: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/onboarding/admin/submissions/<submission_id>/archive', methods=['PATCH'])
@onboarding_admin_required
def archive_submission(submission_id):
    try:
        email = session.get('user', {}).get('email', '').lower()
        perms = get_onboarding_permissions(email)
        if not perms or not perms['can_archive']:
            return jsonify({'error': 'You do not have permission to archive'}), 403

        query = f"UPDATE `{get_full_table_id()}` SET is_archived = TRUE WHERE submission_id = @submission_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("submission_id", "STRING", submission_id)]
        )
        bq_client.query(query, job_config=cfg).result()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error archiving onboarding submission: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/onboarding/admin/submissions/<submission_id>/unarchive', methods=['PATCH'])
@onboarding_admin_required
def unarchive_submission(submission_id):
    try:
        query = f"UPDATE `{get_full_table_id()}` SET is_archived = FALSE WHERE submission_id = @submission_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("submission_id", "STRING", submission_id)]
        )
        bq_client.query(query, job_config=cfg).result()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error unarchiving onboarding submission: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/onboarding/admin/stats', methods=['GET'])
@onboarding_admin_required
def get_stats():
    all_subs = read_all_submissions()
    subs = [s for s in all_subs if not s.get('is_archived')]

    total = len(subs)
    not_started = len([s for s in subs if s.get('onboarding_status') == 'Not Started'])
    in_progress = len([s for s in subs if s.get('onboarding_status') == 'In Progress'])
    complete = len([s for s in subs if s.get('onboarding_status') == 'Complete'])
    needs_accommodation = len([s for s in subs if s.get('ada_accommodation', 'None') != 'None'])

    return jsonify({
        'total': total,
        'not_started': not_started,
        'in_progress': in_progress,
        'complete': complete,
        'needs_accommodation': needs_accommodation,
    })
