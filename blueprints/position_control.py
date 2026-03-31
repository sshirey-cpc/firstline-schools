"""
Position Control Form — Admin Dashboard Blueprint
Ported from standalone position-control-form/app.py
"""

import os
import uuid
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, session
from google.cloud import bigquery

from config import (
    PROJECT_ID, PCF_DATASET_ID, PCF_TABLE_ID,
    PC_DATASET_ID, PC_TABLE_ID,
    SMTP_EMAIL, SMTP_PASSWORD, SMTP_SERVER, SMTP_PORT,
)
from extensions import bq_client
from auth import get_pcf_access, get_pcf_permissions

logger = logging.getLogger(__name__)

bp = Blueprint('position_control', __name__)

# ── Helpers ──

def get_full_table_id():
    return f"{PROJECT_ID}.{PCF_DATASET_ID}.{PCF_TABLE_ID}"


def pcf_admin_required(f):
    """Require login + PCF role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        email = session['user'].get('email', '').lower()
        if not get_pcf_access(email):
            return jsonify({'error': 'Position Control access required'}), 403
        return f(*args, **kwargs)
    return decorated


def row_to_dict(row):
    return {
        'request_id': row.request_id,
        'submitted_at': row.submitted_at.isoformat() if row.submitted_at else '',
        'requestor_name': row.requestor_name or '',
        'requestor_email': row.requestor_email or '',
        'request_type': row.request_type or '',
        'hours_status': row.hours_status or '',
        'position_title': row.position_title or '',
        'reports_to': row.reports_to or '',
        'requested_amount': row.requested_amount or '',
        'employee_name': row.employee_name or '',
        'justification': row.justification or '',
        'sped_reviewed': row.sped_reviewed or '',
        'school_year': row.school_year or '',
        'duration': row.duration or '',
        'payment_dates': row.payment_dates or '',
        'ceo_approval': row.ceo_approval or '',
        'finance_approval': row.finance_approval or '',
        'talent_approval': row.talent_approval or '',
        'hr_approval': row.hr_approval or '',
        'final_status': row.final_status or '',
        'offer_sent': row.offer_sent.isoformat() if row.offer_sent else '',
        'offer_signed': row.offer_signed.isoformat() if row.offer_signed else '',
        'admin_notes': row.admin_notes or '',
        'position_id': row.position_id or '',
        'updated_at': row.updated_at.isoformat() if row.updated_at else '',
        'updated_by': row.updated_by or '',
        'is_archived': bool(getattr(row, 'is_archived', False) or False),
        'school': getattr(row, 'school', '') or '',
        'hire_type': getattr(row, 'hire_type', '') or '',
        'employee_email': getattr(row, 'employee_email', '') or '',
        'candidate_email': getattr(row, 'candidate_email', '') or '',
        'candidate_position_id': getattr(row, 'candidate_position_id', '') or '',
        'linked_position_id': getattr(row, 'linked_position_id', '') or '',
    }


def read_all_requests():
    try:
        query = f"SELECT * FROM `{get_full_table_id()}` ORDER BY submitted_at DESC"
        return [row_to_dict(r) for r in bq_client.query(query).result()]
    except Exception as e:
        logger.error(f"Error reading PCF requests: {e}")
        return []


def get_request_by_id(request_id):
    try:
        query = f"SELECT * FROM `{get_full_table_id()}` WHERE request_id = @request_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
        )
        for row in bq_client.query(query, job_config=cfg).result():
            return row_to_dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting PCF request: {e}")
        return None


def update_request(request_id, updates):
    try:
        clauses, params = [], [bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
        for field, value in updates.items():
            p = f"param_{field}"
            if field in ('offer_sent', 'offer_signed'):
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
        query = f"UPDATE `{get_full_table_id()}` SET {', '.join(clauses)} WHERE request_id = @request_id"
        bq_client.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return True
    except Exception as e:
        logger.error(f"Error updating PCF request: {e}")
        return False


def send_email(to_email, subject, html_body, cc_emails=None):
    if not SMTP_PASSWORD:
        logger.warning("SMTP_PASSWORD not configured, skipping email")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"FirstLine Schools Talent <{SMTP_EMAIL}>"
        msg['To'] = to_email
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, [to_email] + (cc_emails or []), msg.as_string())
        logger.info(f"PCF email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"PCF email failed: {e}")
        return False


# ── Routes ──

@bp.route('/position-control-dashboard')
def dashboard():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from app import serve_html
    return serve_html(os.path.join(root, 'position-control-dashboard.html'))


@bp.route('/api/pcf/admin/requests', methods=['GET'])
@pcf_admin_required
def get_all_requests_route():
    return jsonify({'requests': read_all_requests()})


@bp.route('/api/pcf/admin/requests/<request_id>', methods=['PATCH'])
@pcf_admin_required
def update_request_status(request_id):
    try:
        data = request.json
        user = session.get('user', {})
        email = user.get('email', '').lower()
        perms = get_pcf_permissions(email)

        if not perms:
            return jsonify({'error': 'No permissions configured for this user'}), 403

        updates = {}

        # Approval fields — only allow fields the user has permission for
        for field in ['ceo_approval', 'finance_approval', 'talent_approval', 'hr_approval']:
            if field in data:
                if field not in perms['can_approve']:
                    return jsonify({'error': f'You do not have permission to set {field}'}), 403
                if data[field] not in ['Pending', 'Approved', 'Denied']:
                    return jsonify({'error': f'Invalid value for {field}'}), 400
                updates[field] = data[field]

        # Final status
        if 'final_status' in data:
            if not perms['can_edit_final']:
                return jsonify({'error': 'You do not have permission to set final status'}), 403
            if data['final_status'] not in ['Pending', 'Approved', 'Denied', 'Withdrawn']:
                return jsonify({'error': 'Invalid final_status'}), 400
            updates['final_status'] = data['final_status']

        # Date fields
        for field in ['offer_sent', 'offer_signed']:
            if field in data:
                if not perms['can_edit_dates']:
                    return jsonify({'error': 'You do not have permission to edit offer dates'}), 403
                updates[field] = data[field]

        # Admin notes
        if 'admin_notes' in data:
            updates['admin_notes'] = data['admin_notes']

        # Audit
        updates['updated_at'] = datetime.now().isoformat()
        updates['updated_by'] = user.get('email', 'Unknown')

        if update_request(request_id, updates):
            return jsonify({'success': True})
        return jsonify({'error': 'Request not found'}), 404
    except Exception as e:
        logger.error(f"Error updating PCF request: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/pcf/admin/requests/<request_id>', methods=['DELETE'])
@pcf_admin_required
def delete_request(request_id):
    try:
        email = session.get('user', {}).get('email', '').lower()
        perms = get_pcf_permissions(email)
        if not perms or not perms['can_delete']:
            return jsonify({'error': 'Only super admins can delete requests'}), 403

        query = f"DELETE FROM `{get_full_table_id()}` WHERE request_id = @request_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
        )
        bq_client.query(query, job_config=cfg).result()
        logger.info(f"Deleted PCF request {request_id}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting PCF request: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/pcf/admin/requests/<request_id>/archive', methods=['PATCH'])
@pcf_admin_required
def archive_request(request_id):
    try:
        query = f"UPDATE `{get_full_table_id()}` SET is_archived = TRUE WHERE request_id = @request_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
        )
        bq_client.query(query, job_config=cfg).result()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error archiving PCF request: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/pcf/admin/requests/<request_id>/unarchive', methods=['PATCH'])
@pcf_admin_required
def unarchive_request(request_id):
    try:
        query = f"UPDATE `{get_full_table_id()}` SET is_archived = FALSE WHERE request_id = @request_id"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("request_id", "STRING", request_id)]
        )
        bq_client.query(query, job_config=cfg).result()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error unarchiving PCF request: {e}")
        return jsonify({'error': 'Server error'}), 500


@bp.route('/api/pcf/admin/stats', methods=['GET'])
@pcf_admin_required
def get_stats():
    all_requests = read_all_requests()
    reqs = [r for r in all_requests if not r.get('is_archived')]

    total = len(reqs)
    pending = len([r for r in reqs if r.get('final_status') == 'Pending'])
    approved = len([r for r in reqs if r.get('final_status') == 'Approved'])
    denied = len([r for r in reqs if r.get('final_status') == 'Denied'])
    awaiting_offer = len([
        r for r in reqs
        if r.get('final_status') == 'Approved' and not r.get('offer_sent')
    ])

    return jsonify({
        'total': total,
        'pending': pending,
        'approved': approved,
        'denied': denied,
        'awaiting_offer': awaiting_offer,
    })


@bp.route('/api/pcf/admin/requests/<request_id>/create-position', methods=['POST'])
@pcf_admin_required
def create_position(request_id):
    try:
        email = session.get('user', {}).get('email', '').lower()
        perms = get_pcf_permissions(email)
        if not perms or not perms['can_create_position']:
            return jsonify({'error': 'You do not have permission to create positions'}), 403

        req = get_request_by_id(request_id)
        if not req:
            return jsonify({'error': 'Request not found'}), 404
        if req.get('final_status') != 'Approved':
            return jsonify({'error': 'Request must be fully approved before creating a position'}), 400
        if req.get('position_id'):
            return jsonify({'error': 'Position already created for this request', 'position_id': req['position_id']}), 400

        user = session.get('user', {})
        position_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        school_year = req.get('school_year', '')
        start_year = school_year.replace(' SY', '') if school_year else '25-26'

        pc_table = f"{PROJECT_ID}.{PC_DATASET_ID}.{PC_TABLE_ID}"
        pc_query = f"""
        INSERT INTO `{pc_table}` (
            position_id, school, job_title, current_status,
            start_year, notes, candidate_name, created_at, updated_at, updated_by
        ) VALUES (
            @position_id, @school, @job_title, @current_status,
            @start_year, @notes, @candidate_name, @created_at, @updated_at, @updated_by
        )
        """

        pc_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("position_id", "STRING", position_id),
                bigquery.ScalarQueryParameter("school", "STRING", ""),
                bigquery.ScalarQueryParameter("job_title", "STRING", req.get('position_title', '')),
                bigquery.ScalarQueryParameter("current_status", "STRING", "Open"),
                bigquery.ScalarQueryParameter("start_year", "STRING", start_year),
                bigquery.ScalarQueryParameter("notes", "STRING", f"Created from PCF request {request_id}"),
                bigquery.ScalarQueryParameter("candidate_name", "STRING", req.get('employee_name', '')),
                bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", datetime.now()),
                bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", datetime.now()),
                bigquery.ScalarQueryParameter("updated_by", "STRING", user.get('email', 'system')),
            ]
        )

        bq_client.query(pc_query, job_config=pc_config).result()

        update_request(request_id, {
            'position_id': position_id,
            'updated_at': now,
            'updated_by': user.get('email', 'system'),
        })

        logger.info(f"Created position {position_id} from PCF request {request_id}")
        return jsonify({'success': True, 'position_id': position_id})
    except Exception as e:
        logger.error(f"Error creating position: {e}")
        return jsonify({'error': f'Failed to create position: {str(e)}'}), 500


@bp.route('/api/pcf/job-titles', methods=['GET'])
@pcf_admin_required
def get_job_titles():
    try:
        pc_table = f"{PROJECT_ID}.{PC_DATASET_ID}.{PC_TABLE_ID}"
        query = f"""
        SELECT DISTINCT job_title
        FROM `{pc_table}`
        WHERE job_title IS NOT NULL AND job_title != ''
        ORDER BY job_title
        """
        results = bq_client.query(query).result()
        return jsonify({'titles': [row.job_title for row in results]})
    except Exception as e:
        logger.error(f"Error fetching job titles: {e}")
        return jsonify({'titles': []})
