"""Supervisor Dashboard routes (main dashboard)."""

import os
import logging
from flask import Blueprint, jsonify, request, session, send_from_directory
from google.cloud import bigquery

from config import PROJECT_ID, DATASET_ID, TABLE_ID, CURRENT_SY_START
from extensions import bq_client
from auth import (
    login_required, is_admin,
    get_supervisor_name_for_email, get_accessible_supervisors,
)

logger = logging.getLogger(__name__)

bp = Blueprint('supervisor', __name__)


def _check_employee_access(email):
    """Check if the current user has permission to view data for the given employee email."""
    user = session.get('user', {})
    if user.get('is_admin'):
        return True

    accessible_supervisors = user.get('accessible_supervisors', [])
    if not accessible_supervisors:
        return False

    # Check if the employee's supervisor is in the user's accessible list
    query = f"""
        SELECT Supervisor_Name__Unsecured_
        FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}`
        WHERE LOWER(Email_Address) = LOWER(@email)
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("email", "STRING", email)
        ]
    )
    results = list(bq_client.query(query, job_config=job_config).result())
    if not results:
        return False

    return results[0].Supervisor_Name__Unsecured_ in accessible_supervisors

HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@bp.route('/')
def index():
    """Serve the main dashboard HTML file"""
    return send_from_directory(HTML_DIR, 'index.html')


@bp.route('/api/supervisors', methods=['GET'])
@login_required
def get_supervisors():
    """
    Get list of supervisors the logged-in user can access.
    - Admins get all supervisors
    - Regular supervisors get themselves + their downline (hierarchical access)
    Returns: JSON array of supervisor names the user can view.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        user = session.get('user', {})
        accessible_supervisors = user.get('accessible_supervisors', [])

        if accessible_supervisors:
            logger.info(f"Returning {len(accessible_supervisors)} accessible supervisors for {user.get('email')}")
            return jsonify(accessible_supervisors)

        logger.warning(f"No accessible supervisors for user: {user.get('email')}")
        return jsonify([])

    except Exception as e:
        logger.error(f"Error fetching supervisors: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/refresh-session', methods=['POST'])
@login_required
def refresh_session():
    """
    Refresh the user's session data by recalculating accessible supervisors.
    This is useful when supervisor hierarchy data changes without requiring re-login.
    """
    try:
        user = session.get('user', {})
        email = user.get('email')

        if not email:
            return jsonify({'error': 'No user email in session'}), 400

        supervisor_name = get_supervisor_name_for_email(email)
        accessible_supervisors = get_accessible_supervisors(email, supervisor_name)

        session['user'] = {
            'email': email,
            'supervisor_name': supervisor_name,
            'is_admin': is_admin(email),
            'accessible_supervisors': accessible_supervisors
        }

        logger.info(f"Session refreshed for {email}: {len(accessible_supervisors)} accessible supervisors")

        return jsonify({
            'success': True,
            'supervisor_name': supervisor_name,
            'accessible_supervisors': accessible_supervisors,
            'count': len(accessible_supervisors)
        })

    except Exception as e:
        logger.error(f"Error refreshing session: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/team/staff', methods=['GET'])
@login_required
def get_team_staff():
    """
    Get all staff members across ALL accessible supervisors, plus the user themselves.
    No supervisor parameter needed — uses the session's accessible_supervisors directly.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    accessible_supervisors = user.get('accessible_supervisors', [])
    user_email = user.get('email', '')

    if not accessible_supervisors:
        return jsonify([])

    try:
        query = f"""
            WITH latest_accruals AS (
                SELECT
                    `Person Number` as Person_Number,
                    `Accrual Code Name` as Accrual_Code_Name,
                    (`Earned to Date _Hours_` + `Pending Grants _Hours_`) as max_hours,
                    (`Earned to Date _Hours_` + `Pending Grants _Hours_` - COALESCE(`Taken to Date _Hours_`, 0)) as remaining_hours
                FROM `{PROJECT_ID}.payroll_validation.accrual_balance`
                WHERE `Date Balance as of Date` = (
                    SELECT MAX(`Date Balance as of Date`)
                    FROM `{PROJECT_ID}.payroll_validation.accrual_balance`
                )
            ),
            accrual_pivoted AS (
                SELECT
                    Person_Number,
                    MAX(CASE WHEN Accrual_Code_Name = 'PTO' THEN remaining_hours END) as pto_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'PTO' THEN max_hours END) as pto_max,
                    MAX(CASE WHEN Accrual_Code_Name = 'Vacation' THEN remaining_hours END) as vacation_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'Vacation' THEN max_hours END) as vacation_max,
                    MAX(CASE WHEN Accrual_Code_Name = 'Personal Time' THEN remaining_hours END) as personal_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'Personal Time' THEN max_hours END) as personal_max,
                    MAX(CASE WHEN Accrual_Code_Name = 'Sick' THEN remaining_hours END) as sick_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'Sick' THEN max_hours END) as sick_max
                FROM latest_accruals
                GROUP BY Person_Number
            ),
            sabbatical_apps AS (
                SELECT
                    LOWER(employee_email) as employee_email,
                    application_id,
                    status,
                    start_date,
                    end_date
                FROM `{PROJECT_ID}.sabbatical.applications`
                WHERE status NOT IN ('Denied')
            ),
            classified_obs AS (
                SELECT DISTINCT
                    teacher_internal_id,
                    teacher_name,
                    observer_name,
                    observation_type,
                    observed_at,
                    rubric_form,
                    LOWER(TRIM(teacher_name)) = LOWER(TRIM(observer_name)) AS is_self,
                    CASE WHEN observation_type LIKE '%2%' THEN 2 ELSE 1 END AS form_round,
                    LOWER(TRIM(teacher_name)) = LOWER(TRIM(observer_name))
                        AND observation_type LIKE '%PMAP%' AS is_self_pmap,
                    LOWER(TRIM(teacher_name)) != LOWER(TRIM(observer_name))
                        AND observation_type LIKE '%Self-Reflection%' AS is_other_sr,
                    CASE
                        WHEN (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')
                             AND rubric_form LIKE '%Teacher%' THEN 'teacher'
                        ELSE NULL
                    END AS rubric_role
                FROM `{PROJECT_ID}.{DATASET_ID}.observations_raw_native`
                WHERE teacher_internal_id IS NOT NULL
                AND is_published = 1
                AND observed_at >= '{CURRENT_SY_START}'
            ),
            published_obs_counts AS (
                SELECT
                    teacher_internal_id,
                    COUNT(*) as total_published,
                    COUNTIF(is_self AND form_round = 1) as sr1_finalized,
                    COUNTIF(is_self AND form_round = 2) as sr2_finalized,
                    COUNTIF(NOT is_self AND form_round = 1
                            AND (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')) as pmap1_finalized,
                    COUNTIF(NOT is_self AND form_round = 2
                            AND (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')) as pmap2_finalized,
                    -- Per-icon wrong form flags
                    -- Wrong form: flag only when wrong form is the ONLY version for that round
                    -- SR wrong form = did PMAP as self (self_pmap) but never did a proper SR
                    (COUNTIF(is_self_pmap AND form_round = 1) > 0
                        AND COUNTIF(is_self AND form_round = 1 AND NOT is_self_pmap) = 0) as sr1_wrong_form,
                    (COUNTIF(is_self_pmap AND form_round = 2) > 0
                        AND COUNTIF(is_self AND form_round = 2 AND NOT is_self_pmap) = 0) as sr2_wrong_form,
                    -- PMAP wrong form = supervisor used SR form but never did a proper PMAP
                    (COUNTIF(is_other_sr AND form_round = 1) > 0
                        AND COUNTIF(NOT is_self AND form_round = 1 AND NOT is_other_sr
                            AND (observation_type LIKE '%PMAP%')) = 0) as pmap1_wrong_form,
                    (COUNTIF(is_other_sr AND form_round = 2) > 0
                        AND COUNTIF(NOT is_self AND form_round = 2 AND NOT is_other_sr
                            AND (observation_type LIKE '%PMAP%')) = 0) as pmap2_wrong_form,
                    COUNTIF(rubric_role = 'teacher') as teacher_rubric_count,
                    COUNTIF(rubric_role = 'teacher' AND is_self AND form_round = 1) > 0 as teacher_form_sr1,
                    COUNTIF(rubric_role = 'teacher' AND is_self AND form_round = 2) > 0 as teacher_form_sr2,
                    COUNTIF(rubric_role = 'teacher' AND NOT is_self AND form_round = 1) > 0 as teacher_form_pmap1,
                    COUNTIF(rubric_role = 'teacher' AND NOT is_self AND form_round = 2) > 0 as teacher_form_pmap2
                FROM classified_obs
                GROUP BY teacher_internal_id
            ),
            last_published_obs AS (
                SELECT
                    teacher_internal_id,
                    observation_type as last_published_type,
                    observed_at as last_published_date
                FROM (
                    SELECT
                        teacher_internal_id,
                        observation_type,
                        observed_at,
                        ROW_NUMBER() OVER (PARTITION BY teacher_internal_id ORDER BY observed_at DESC) as rn
                    FROM classified_obs
                )
                WHERE rn = 1
            )
            SELECT
                s.Employee_Number,
                s.first_name,
                s.last_name,
                s.Email_Address,
                s.Date_of_Birth,
                s.Location_Name,
                s.Supervisor_Name__Unsecured_,
                s.Supervisor_Email,
                s.job_title,
                s.Employment_Status,
                s.Last_Hire_Date,
                s.Job_Function,
                s.years_of_service,
                s.pto_hours_left,
                s.vacation_hours_left,
                s.personal_hours_left,
                s.sick_hours_left,
                s.total_goals,
                COALESCE(poc.total_published, 0) as total_observations,
                COALESCE(lpo.last_published_date, s.last_observation_date) as last_observation_date,
                COALESCE(poc.sr1_finalized, 0) as self_reflection_1_count,
                COALESCE(poc.sr2_finalized, 0) as self_reflection_2_count,
                COALESCE(poc.pmap1_finalized, 0) as pmap_1_count,
                COALESCE(poc.pmap2_finalized, 0) as pmap_2_count,
                COALESCE(poc.sr1_wrong_form, FALSE) as sr1_wrong_form,
                COALESCE(poc.sr2_wrong_form, FALSE) as sr2_wrong_form,
                COALESCE(poc.pmap1_wrong_form, FALSE) as pmap1_wrong_form,
                COALESCE(poc.pmap2_wrong_form, FALSE) as pmap2_wrong_form,
                COALESCE(poc.teacher_rubric_count, 0) as teacher_rubric_count,
                COALESCE(poc.teacher_form_sr1, FALSE) as teacher_form_sr1,
                COALESCE(poc.teacher_form_sr2, FALSE) as teacher_form_sr2,
                COALESCE(poc.teacher_form_pmap1, FALSE) as teacher_form_pmap1,
                COALESCE(poc.teacher_form_pmap2, FALSE) as teacher_form_pmap2,
                s.iap_count,
                s.writeup_count,
                COALESCE(lpo.last_published_type, s.last_observation_type) as last_observation_type,
                s.intent_to_return,
                s.intent_response_status,
                s.nps_score,
                CONCAT(s.first_name, ' ', s.last_name) AS Staff_Name,
                a.pto_available,
                a.pto_max,
                a.vacation_available,
                a.vacation_max,
                a.personal_available,
                a.personal_max,
                a.sick_available,
                a.sick_max,
                sml.Salary_or_Hourly,
                sab.application_id as sabbatical_app_id,
                sab.status as sabbatical_status,
                sab.start_date as sabbatical_start,
                sab.end_date as sabbatical_end,
                ol.doc_state as offer_letter_doc_state,
                ol.sent_at as offer_letter_sent_at,
                ol.doc_name as offer_letter_doc_name,
                ol.employee_status as offer_letter_employee_status,
                ol.counter_signer_name as offer_letter_counter_signer,
                ol.counter_signer_status as offer_letter_counter_status
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` s
            LEFT JOIN accrual_pivoted a ON s.Employee_Number = a.Person_Number
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(s.Email_Address) = LOWER(sml.Email_Address)
            LEFT JOIN published_obs_counts poc
                ON s.Employee_Number = CAST(poc.teacher_internal_id AS INT64)
            LEFT JOIN last_published_obs lpo
                ON s.Employee_Number = CAST(lpo.teacher_internal_id AS INT64)
            LEFT JOIN sabbatical_apps sab
                ON LOWER(s.Email_Address) = sab.employee_email
            LEFT JOIN (
                WITH offer_docs AS (
                    SELECT d2.id as doc_id, d2.name as doc_name, d2.state, d2.sent_at,
                           ROW_NUMBER() OVER (PARTITION BY d2.id ORDER BY d2.sent_at DESC) as doc_rn
                    FROM `{PROJECT_ID}.rightsignature.documents` d2
                    WHERE d2.name LIKE "26-27%SY Offer Letter%"
                ),
                offer_signers AS (
                    SELECT od.doc_id, od.doc_name, od.state, od.sent_at,
                           s2.signer_email, s2.signer_name, s2.role_name, s2.status as signer_status
                    FROM offer_docs od
                    JOIN `{PROJECT_ID}.rightsignature.signers` s2 ON od.doc_id = s2.document_id
                    WHERE od.doc_rn = 1
                ),
                employee_offers AS (
                    SELECT
                        emp.signer_email,
                        emp.doc_name,
                        emp.state as doc_state,
                        emp.sent_at,
                        emp.signer_status as employee_status,
                        counter.signer_name as counter_signer_name,
                        counter.signer_status as counter_signer_status,
                        ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(emp.signer_email)) ORDER BY emp.sent_at DESC) as rn
                    FROM offer_signers emp
                    LEFT JOIN offer_signers counter
                        ON emp.doc_id = counter.doc_id AND counter.role_name = 'signer2'
                    WHERE emp.role_name = 'signer1'
                )
                SELECT signer_email, doc_name, doc_state, sent_at,
                       employee_status, counter_signer_name, counter_signer_status
                FROM employee_offers WHERE rn = 1
            ) ol ON LOWER(s.Email_Address) = LOWER(ol.signer_email)
            WHERE s.Supervisor_Name__Unsecured_ IN UNNEST(@supervisors)
               OR LOWER(s.Email_Address) = LOWER(@user_email)
            ORDER BY s.last_name, s.first_name
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("supervisors", "STRING", accessible_supervisors),
                bigquery.ScalarQueryParameter("user_email", "STRING", user_email),
            ]
        )

        logger.info(f"Fetching team staff data for {user_email} ({len(accessible_supervisors)} supervisors)")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        staff_data = []
        for row in results:
            staff_member = dict(row.items())

            for key, value in staff_member.items():
                if hasattr(value, 'isoformat'):
                    staff_member[key] = value.isoformat()

            staff_data.append(staff_member)

        logger.info(f"Found {len(staff_data)} total team staff members for {user_email}")

        return jsonify(staff_data)

    except Exception as e:
        logger.error(f"Error fetching team staff for {user_email}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/team/action-steps', methods=['GET'])
@login_required
def get_team_action_steps():
    """
    Get action steps for ALL staff across all accessible supervisors.
    Returns a dict of email -> list of action steps.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    accessible_supervisors = user.get('accessible_supervisors', [])

    if not accessible_supervisors:
        return jsonify({})

    try:
        query = f"""
            SELECT
                a._id,
                a.name,
                a.user_email,
                a.user_name,
                a.creator_name,
                a.creator_email,
                a.progress_percent,
                a.tags,
                a.created,
                a.lastModified
            FROM `{PROJECT_ID}.{DATASET_ID}.ldg_action_steps` a
            INNER JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` s
                ON LOWER(a.user_email) = LOWER(s.Email_Address)
            WHERE s.Supervisor_Name__Unsecured_ IN UNNEST(@supervisors)
            AND a.archivedAt IS NULL
            AND a.created >= '{CURRENT_SY_START}'
            ORDER BY a.user_email, a.created DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("supervisors", "STRING", accessible_supervisors),
            ]
        )

        logger.info(f"Fetching team action steps for {len(accessible_supervisors)} supervisors")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        action_steps = {}
        for row in results:
            email = row.user_email.lower() if row.user_email else ''
            step = {
                'id': row._id,
                'name': row.name,
                'user_name': row.user_name,
                'creator_name': row.creator_name,
                'creator_email': row.creator_email,
                'progress_percent': row.progress_percent,
                'tags': row.tags,
                'created': row.created.isoformat() if row.created else None,
                'lastModified': row.lastModified.isoformat() if row.lastModified else None
            }
            if email not in action_steps:
                action_steps[email] = []
            action_steps[email].append(step)

        logger.info(f"Found action steps for {len(action_steps)} staff members across all supervisors")
        return jsonify(action_steps)

    except Exception as e:
        logger.error(f"Error fetching team action steps: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/staff/<supervisor_name>', methods=['GET'])
@login_required
def get_staff(supervisor_name):
    """
    Get all staff members for a specific supervisor.
    Authorization: User can only access supervisors in their accessible list.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    accessible_supervisors = user.get('accessible_supervisors', [])

    if supervisor_name not in accessible_supervisors:
        logger.warning(
            f"Authorization denied: user {user.get('email')} "
            f"tried to access {supervisor_name} (not in their {len(accessible_supervisors)} accessible supervisors)"
        )
        return jsonify({'error': 'Access denied. You do not have permission to view this team.'}), 403

    try:
        query = f"""
            WITH latest_accruals AS (
                SELECT
                    `Person Number` as Person_Number,
                    `Accrual Code Name` as Accrual_Code_Name,
                    (`Earned to Date _Hours_` + `Pending Grants _Hours_`) as max_hours,
                    (`Earned to Date _Hours_` + `Pending Grants _Hours_` - COALESCE(`Taken to Date _Hours_`, 0)) as remaining_hours
                FROM `{PROJECT_ID}.payroll_validation.accrual_balance`
                WHERE `Date Balance as of Date` = (
                    SELECT MAX(`Date Balance as of Date`)
                    FROM `{PROJECT_ID}.payroll_validation.accrual_balance`
                )
            ),
            accrual_pivoted AS (
                SELECT
                    Person_Number,
                    MAX(CASE WHEN Accrual_Code_Name = 'PTO' THEN remaining_hours END) as pto_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'PTO' THEN max_hours END) as pto_max,
                    MAX(CASE WHEN Accrual_Code_Name = 'Vacation' THEN remaining_hours END) as vacation_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'Vacation' THEN max_hours END) as vacation_max,
                    MAX(CASE WHEN Accrual_Code_Name = 'Personal Time' THEN remaining_hours END) as personal_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'Personal Time' THEN max_hours END) as personal_max,
                    MAX(CASE WHEN Accrual_Code_Name = 'Sick' THEN remaining_hours END) as sick_available,
                    MAX(CASE WHEN Accrual_Code_Name = 'Sick' THEN max_hours END) as sick_max
                FROM latest_accruals
                GROUP BY Person_Number
            ),
            sabbatical_apps AS (
                SELECT
                    LOWER(employee_email) as employee_email,
                    application_id,
                    status,
                    start_date,
                    end_date
                FROM `{PROJECT_ID}.sabbatical.applications`
                WHERE status NOT IN ('Denied')
            ),
            classified_obs AS (
                SELECT DISTINCT
                    teacher_internal_id,
                    teacher_name,
                    observer_name,
                    observation_type,
                    observed_at,
                    rubric_form,
                    LOWER(TRIM(teacher_name)) = LOWER(TRIM(observer_name)) AS is_self,
                    CASE WHEN observation_type LIKE '%2%' THEN 2 ELSE 1 END AS form_round,
                    LOWER(TRIM(teacher_name)) = LOWER(TRIM(observer_name))
                        AND observation_type LIKE '%PMAP%' AS is_self_pmap,
                    LOWER(TRIM(teacher_name)) != LOWER(TRIM(observer_name))
                        AND observation_type LIKE '%Self-Reflection%' AS is_other_sr,
                    CASE
                        WHEN (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')
                             AND rubric_form LIKE '%Teacher%' THEN 'teacher'
                        ELSE NULL
                    END AS rubric_role
                FROM `{PROJECT_ID}.{DATASET_ID}.observations_raw_native`
                WHERE teacher_internal_id IS NOT NULL
                AND is_published = 1
                AND observed_at >= '{CURRENT_SY_START}'
            ),
            published_obs_counts AS (
                SELECT
                    teacher_internal_id,
                    COUNT(*) as total_published,
                    COUNTIF(is_self AND form_round = 1) as sr1_finalized,
                    COUNTIF(is_self AND form_round = 2) as sr2_finalized,
                    COUNTIF(NOT is_self AND form_round = 1
                            AND (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')) as pmap1_finalized,
                    COUNTIF(NOT is_self AND form_round = 2
                            AND (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')) as pmap2_finalized,
                    -- Per-icon wrong form flags
                    -- Wrong form: flag only when wrong form is the ONLY version for that round
                    -- SR wrong form = did PMAP as self (self_pmap) but never did a proper SR
                    (COUNTIF(is_self_pmap AND form_round = 1) > 0
                        AND COUNTIF(is_self AND form_round = 1 AND NOT is_self_pmap) = 0) as sr1_wrong_form,
                    (COUNTIF(is_self_pmap AND form_round = 2) > 0
                        AND COUNTIF(is_self AND form_round = 2 AND NOT is_self_pmap) = 0) as sr2_wrong_form,
                    -- PMAP wrong form = supervisor used SR form but never did a proper PMAP
                    (COUNTIF(is_other_sr AND form_round = 1) > 0
                        AND COUNTIF(NOT is_self AND form_round = 1 AND NOT is_other_sr
                            AND (observation_type LIKE '%PMAP%')) = 0) as pmap1_wrong_form,
                    (COUNTIF(is_other_sr AND form_round = 2) > 0
                        AND COUNTIF(NOT is_self AND form_round = 2 AND NOT is_other_sr
                            AND (observation_type LIKE '%PMAP%')) = 0) as pmap2_wrong_form,
                    COUNTIF(rubric_role = 'teacher') as teacher_rubric_count,
                    COUNTIF(rubric_role = 'teacher' AND is_self AND form_round = 1) > 0 as teacher_form_sr1,
                    COUNTIF(rubric_role = 'teacher' AND is_self AND form_round = 2) > 0 as teacher_form_sr2,
                    COUNTIF(rubric_role = 'teacher' AND NOT is_self AND form_round = 1) > 0 as teacher_form_pmap1,
                    COUNTIF(rubric_role = 'teacher' AND NOT is_self AND form_round = 2) > 0 as teacher_form_pmap2
                FROM classified_obs
                GROUP BY teacher_internal_id
            ),
            last_published_obs AS (
                SELECT
                    teacher_internal_id,
                    observation_type as last_published_type,
                    observed_at as last_published_date
                FROM (
                    SELECT
                        teacher_internal_id,
                        observation_type,
                        observed_at,
                        ROW_NUMBER() OVER (PARTITION BY teacher_internal_id ORDER BY observed_at DESC) as rn
                    FROM classified_obs
                )
                WHERE rn = 1
            )
            SELECT
                s.Employee_Number,
                s.first_name,
                s.last_name,
                s.Email_Address,
                s.Date_of_Birth,
                s.Location_Name,
                s.Supervisor_Name__Unsecured_,
                s.Supervisor_Email,
                s.job_title,
                s.Employment_Status,
                s.Last_Hire_Date,
                s.Job_Function,
                s.years_of_service,
                s.pto_hours_left,
                s.vacation_hours_left,
                s.personal_hours_left,
                s.sick_hours_left,
                s.total_goals,
                COALESCE(poc.total_published, 0) as total_observations,
                COALESCE(lpo.last_published_date, s.last_observation_date) as last_observation_date,
                COALESCE(poc.sr1_finalized, 0) as self_reflection_1_count,
                COALESCE(poc.sr2_finalized, 0) as self_reflection_2_count,
                COALESCE(poc.pmap1_finalized, 0) as pmap_1_count,
                COALESCE(poc.pmap2_finalized, 0) as pmap_2_count,
                COALESCE(poc.sr1_wrong_form, FALSE) as sr1_wrong_form,
                COALESCE(poc.sr2_wrong_form, FALSE) as sr2_wrong_form,
                COALESCE(poc.pmap1_wrong_form, FALSE) as pmap1_wrong_form,
                COALESCE(poc.pmap2_wrong_form, FALSE) as pmap2_wrong_form,
                COALESCE(poc.teacher_rubric_count, 0) as teacher_rubric_count,
                COALESCE(poc.teacher_form_sr1, FALSE) as teacher_form_sr1,
                COALESCE(poc.teacher_form_sr2, FALSE) as teacher_form_sr2,
                COALESCE(poc.teacher_form_pmap1, FALSE) as teacher_form_pmap1,
                COALESCE(poc.teacher_form_pmap2, FALSE) as teacher_form_pmap2,
                s.iap_count,
                s.writeup_count,
                COALESCE(lpo.last_published_type, s.last_observation_type) as last_observation_type,
                s.intent_to_return,
                s.intent_response_status,
                s.nps_score,
                CONCAT(s.first_name, ' ', s.last_name) AS Staff_Name,
                a.pto_available,
                a.pto_max,
                a.vacation_available,
                a.vacation_max,
                a.personal_available,
                a.personal_max,
                a.sick_available,
                a.sick_max,
                sml.Salary_or_Hourly,
                sab.application_id as sabbatical_app_id,
                sab.status as sabbatical_status,
                sab.start_date as sabbatical_start,
                sab.end_date as sabbatical_end,
                ol.doc_state as offer_letter_doc_state,
                ol.sent_at as offer_letter_sent_at,
                ol.doc_name as offer_letter_doc_name,
                ol.employee_status as offer_letter_employee_status,
                ol.counter_signer_name as offer_letter_counter_signer,
                ol.counter_signer_status as offer_letter_counter_status
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` s
            LEFT JOIN accrual_pivoted a ON s.Employee_Number = a.Person_Number
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(s.Email_Address) = LOWER(sml.Email_Address)
            LEFT JOIN published_obs_counts poc
                ON s.Employee_Number = CAST(poc.teacher_internal_id AS INT64)
            LEFT JOIN last_published_obs lpo
                ON s.Employee_Number = CAST(lpo.teacher_internal_id AS INT64)
            LEFT JOIN sabbatical_apps sab
                ON LOWER(s.Email_Address) = sab.employee_email
            LEFT JOIN (
                WITH offer_docs AS (
                    SELECT d2.id as doc_id, d2.name as doc_name, d2.state, d2.sent_at,
                           ROW_NUMBER() OVER (PARTITION BY d2.id ORDER BY d2.sent_at DESC) as doc_rn
                    FROM `{PROJECT_ID}.rightsignature.documents` d2
                    WHERE d2.name LIKE "26-27%SY Offer Letter%"
                ),
                offer_signers AS (
                    SELECT od.doc_id, od.doc_name, od.state, od.sent_at,
                           s2.signer_email, s2.signer_name, s2.role_name, s2.status as signer_status
                    FROM offer_docs od
                    JOIN `{PROJECT_ID}.rightsignature.signers` s2 ON od.doc_id = s2.document_id
                    WHERE od.doc_rn = 1
                ),
                employee_offers AS (
                    SELECT
                        emp.signer_email,
                        emp.doc_name,
                        emp.state as doc_state,
                        emp.sent_at,
                        emp.signer_status as employee_status,
                        counter.signer_name as counter_signer_name,
                        counter.signer_status as counter_signer_status,
                        ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(emp.signer_email)) ORDER BY emp.sent_at DESC) as rn
                    FROM offer_signers emp
                    LEFT JOIN offer_signers counter
                        ON emp.doc_id = counter.doc_id AND counter.role_name = 'signer2'
                    WHERE emp.role_name = 'signer1'
                )
                SELECT signer_email, doc_name, doc_state, sent_at,
                       employee_status, counter_signer_name, counter_signer_status
                FROM employee_offers WHERE rn = 1
            ) ol ON LOWER(s.Email_Address) = LOWER(ol.signer_email)
            WHERE s.Supervisor_Name__Unsecured_ = @supervisor
            ORDER BY s.last_name, s.first_name
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("supervisor", "STRING", supervisor_name)
            ]
        )

        logger.info(f"Fetching staff data for supervisor: {supervisor_name}")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        staff_data = []
        for row in results:
            staff_member = dict(row.items())

            for key, value in staff_member.items():
                if hasattr(value, 'isoformat'):
                    staff_member[key] = value.isoformat()

            staff_data.append(staff_member)

        logger.info(f"Found {len(staff_data)} staff members for {supervisor_name}")

        return jsonify(staff_data)

    except Exception as e:
        logger.error(f"Error fetching staff for {supervisor_name}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/itr-detail/<email>', methods=['GET'])
@login_required
def get_itr_detail(email):
    """
    Get Intent to Return detail for a specific employee by email.
    Returns detailed ITR survey response data from native table.
    """
    if not _check_employee_access(email):
        return jsonify({'error': 'Access denied. You do not have permission to view this employee.'}), 403

    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                Email_Address,
                Timestamp,
                Return,
                Return_Role,
                Return_Role_Preference,
                Return_Role_Preference_Other,
                Yes_Decision_Factors,
                Yes_NPS,
                Yes_Top_Factors_Recommend_FLS,
                Yes_Adult_Culture_Open,
                Yes_Improve_Retention_Open,
                Maybe_Decision_Factors,
                Maybe_NPS,
                Maybe_Top_Factors_Recommend_FLS,
                Maybe_Adult_Culture_Open,
                Maybe_Improve_Retention_Open,
                No_Decision_Factors,
                No_NPS,
                No_Top_Factors_Recommend_FLS,
                No_Adult_Culture_Open,
                No_Improve_Retention_Open
            FROM `{PROJECT_ID}.intent_to_return.intent_to_return_native`
            WHERE LOWER(Email_Address) = LOWER(@email)
            LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )

        logger.info(f"Fetching ITR detail for: {email}")
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())

        if not results:
            return jsonify({'error': 'No ITR data found for this employee'}), 404

        row = results[0]
        intent = row.Return

        if intent == 'Yes':
            nps_score = row.Yes_NPS
            decision_factors = row.Yes_Decision_Factors
            top_factors = row.Yes_Top_Factors_Recommend_FLS
            culture_feedback = row.Yes_Adult_Culture_Open
            retention_feedback = row.Yes_Improve_Retention_Open
        elif intent == 'No':
            nps_score = row.No_NPS
            decision_factors = row.No_Decision_Factors
            top_factors = row.No_Top_Factors_Recommend_FLS
            culture_feedback = row.No_Adult_Culture_Open
            retention_feedback = row.No_Improve_Retention_Open
        else:
            nps_score = row.Maybe_NPS
            decision_factors = row.Maybe_Decision_Factors
            top_factors = row.Maybe_Top_Factors_Recommend_FLS
            culture_feedback = row.Maybe_Adult_Culture_Open
            retention_feedback = row.Maybe_Improve_Retention_Open

        nps_category = None
        if nps_score is not None:
            if nps_score >= 9:
                nps_category = 'Promoter'
            elif nps_score >= 7:
                nps_category = 'Passive'
            else:
                nps_category = 'Detractor'

        itr_data = {
            'email': row.Email_Address,
            'response_date': row.Timestamp.isoformat() if row.Timestamp else None,
            'intent_to_return': intent,
            'return_role': row.Return_Role,
            'return_role_preference': row.Return_Role_Preference,
            'return_role_preference_other': row.Return_Role_Preference_Other,
            'nps_score': nps_score,
            'nps_category': nps_category,
            'decision_factors': decision_factors,
            'top_factors_recommend_fls': top_factors,
            'adult_culture_feedback': culture_feedback,
            'improve_retention_feedback': retention_feedback
        }

        logger.info(f"Found ITR data for {email}: intent={intent}")
        return jsonify(itr_data)

    except Exception as e:
        logger.error(f"Error fetching ITR detail for {email}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/cert-status', methods=['GET'])
@login_required
def get_cert_status():
    """
    Get certification status for all teachers and leaders.
    Returns a dict of email -> certification info for staff who are certified.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                LOWER(FLS_Email) as email,
                certification_status,
                active_certifications,
                active_qualifications,
                earliest_active_expiration,
                days_until_earliest_expiration
            FROM `{PROJECT_ID}.talent_certification.staff_with_certifications_native`
            WHERE certification_status = 'Certified'
            AND (
                Title LIKE '%Teacher%'
                OR Title LIKE '%Principal%'
                OR Title LIKE '%Dean%'
                OR Title LIKE '%Director%'
                OR Title LIKE '%Content Lead%'
                OR Title LIKE '%Coordinator%'
            )
        """

        logger.info("Fetching certification status for teachers/leaders")
        query_job = bq_client.query(query)
        results = query_job.result()

        cert_status = {}
        for row in results:
            cert_status[row.email] = {
                'status': row.certification_status,
                'active_count': row.active_certifications,
                'qualifications': row.active_qualifications,
                'earliest_expiration': row.earliest_active_expiration.isoformat() if row.earliest_active_expiration else None,
                'days_until_expiration': row.days_until_earliest_expiration
            }

        logger.info(f"Found {len(cert_status)} certified teachers/leaders")
        return jsonify(cert_status)

    except Exception as e:
        logger.error(f"Error fetching certification status: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/cert-detail/<email>', methods=['GET'])
@login_required
def get_cert_detail(email):
    """
    Get detailed certification information for a specific staff member.
    Returns all certifications (active and expired) for the popup modal.
    """
    if not _check_employee_access(email):
        return jsonify({'error': 'Access denied. You do not have permission to view this employee.'}), 403

    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        summary_query = f"""
            SELECT
                First_Name,
                Last_Name,
                Title,
                School_Site,
                certification_status,
                total_certifications,
                active_certifications,
                expired_certifications,
                active_qualifications,
                earliest_active_expiration,
                days_until_earliest_expiration
            FROM `{PROJECT_ID}.talent_certification.staff_with_certifications_native`
            WHERE LOWER(FLS_Email) = LOWER(@email)
            LIMIT 1
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )

        query_job = bq_client.query(summary_query, job_config=job_config)
        summary_results = list(query_job.result())

        if not summary_results:
            return jsonify({'error': 'No certification data found for this employee'}), 404

        summary = summary_results[0]

        detail_query = f"""
            SELECT
                Category_Name,
                Qualification_Name,
                Certification_Number,
                Status,
                Earn_Date,
                Expire_Date,
                days_until_expiration,
                expiration_status
            FROM `{PROJECT_ID}.talent_certification.staff_certifications_detail_native`
            WHERE LOWER(FLS_Email) = LOWER(@email)
            ORDER BY
                CASE WHEN Status = 'Active' THEN 0 ELSE 1 END,
                Expire_Date DESC
        """

        query_job = bq_client.query(detail_query, job_config=job_config)
        detail_results = query_job.result()

        certifications = []
        for row in detail_results:
            certifications.append({
                'category': row.Category_Name,
                'qualification': row.Qualification_Name,
                'certification_number': row.Certification_Number,
                'status': row.Status,
                'earn_date': row.Earn_Date.isoformat() if row.Earn_Date else None,
                'expire_date': row.Expire_Date.isoformat() if row.Expire_Date else None,
                'days_until_expiration': row.days_until_expiration,
                'expiration_status': row.expiration_status
            })

        cert_data = {
            'name': f"{summary.First_Name} {summary.Last_Name}",
            'title': summary.Title,
            'school': summary.School_Site,
            'certification_status': summary.certification_status,
            'total_certifications': summary.total_certifications,
            'active_certifications': summary.active_certifications,
            'expired_certifications': summary.expired_certifications,
            'active_qualifications': summary.active_qualifications,
            'earliest_expiration': summary.earliest_active_expiration.isoformat() if summary.earliest_active_expiration else None,
            'days_until_expiration': summary.days_until_earliest_expiration,
            'certifications': certifications
        }

        logger.info(f"Found {len(certifications)} certifications for {email}")
        return jsonify(cert_data)

    except Exception as e:
        logger.error(f"Error fetching certification detail for {email}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/observations/<email>', methods=['GET'])
@login_required
def get_observations(email):
    """
    Get observation history for a specific staff member.
    Returns a list of observations with details.
    """
    if not _check_employee_access(email):
        return jsonify({'error': 'Access denied. You do not have permission to view this employee.'}), 403

    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                teacher_email,
                teacher_name,
                observer_name,
                observation_type,
                observed_at,
                rubric_form,
                school_when_observed,
                MAX(observation_link) as observation_link
            FROM `{PROJECT_ID}.{DATASET_ID}.observations_raw_native`
            WHERE LOWER(teacher_email) = LOWER(@email)
            AND observed_at >= '{CURRENT_SY_START}'
            AND is_published = 1
            GROUP BY teacher_email, teacher_name, observer_name, observation_type, observed_at, rubric_form, school_when_observed
            ORDER BY observed_at DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )

        logger.info(f"Fetching observations for: {email}")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        observations = []
        for row in results:
            link = row.observation_link
            if link:
                link = link.replace('schoolmint', 'leveldata')

            observations.append({
                'teacher_name': row.teacher_name,
                'observer_name': row.observer_name,
                'observation_type': row.observation_type,
                'observed_at': row.observed_at.isoformat() if row.observed_at else None,
                'rubric_form': row.rubric_form,
                'school': row.school_when_observed,
                'link': link
            })

        logger.info(f"Found {len(observations)} observations for {email}")
        return jsonify(observations)

    except Exception as e:
        logger.error(f"Error fetching observations for {email}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/action-steps/<supervisor_name>', methods=['GET'])
@login_required
def get_action_steps(supervisor_name):
    """
    Get the most recent action step for each staff member under a supervisor.
    Returns a dict of email -> action step info.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    accessible_supervisors = user.get('accessible_supervisors', [])

    if not is_admin(user.get('email', '')) and supervisor_name not in accessible_supervisors:
        logger.warning(f"Access denied: {user.get('email')} tried to access {supervisor_name}'s action steps")
        return jsonify({'error': 'Access denied'}), 403

    try:
        query = f"""
            SELECT
                a._id,
                a.name,
                a.user_email,
                a.user_name,
                a.creator_name,
                a.creator_email,
                a.progress_percent,
                a.tags,
                a.created,
                a.lastModified
            FROM `{PROJECT_ID}.{DATASET_ID}.ldg_action_steps` a
            INNER JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` s
                ON LOWER(a.user_email) = LOWER(s.Email_Address)
            WHERE s.Supervisor_Name__Unsecured_ = @supervisor_name
            AND a.archivedAt IS NULL
            AND a.created >= '{CURRENT_SY_START}'
            ORDER BY a.user_email, a.created DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name)
            ]
        )

        logger.info(f"Fetching action steps for supervisor: {supervisor_name}")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        action_steps = {}
        for row in results:
            email = row.user_email.lower() if row.user_email else ''
            step = {
                'id': row._id,
                'name': row.name,
                'user_name': row.user_name,
                'creator_name': row.creator_name,
                'creator_email': row.creator_email,
                'progress_percent': row.progress_percent,
                'tags': row.tags,
                'created': row.created.isoformat() if row.created else None,
                'lastModified': row.lastModified.isoformat() if row.lastModified else None
            }
            if email not in action_steps:
                action_steps[email] = []
            action_steps[email].append(step)

        logger.info(f"Found action steps for {len(action_steps)} staff members for {supervisor_name}")
        return jsonify(action_steps)

    except Exception as e:
        logger.error(f"Error fetching action steps for {supervisor_name}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/meetings/<supervisor_name>', methods=['GET'])
@login_required
def get_meetings(supervisor_name):
    """
    Get the most recent meetings for each staff member under a supervisor.
    Returns a dict of email -> list of meetings.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    accessible_supervisors = user.get('accessible_supervisors', [])

    if not is_admin(user.get('email', '')) and supervisor_name not in accessible_supervisors:
        logger.warning(f"Access denied: {user.get('email')} tried to access {supervisor_name}'s meetings")
        return jsonify({'error': 'Access denied'}), 403

    try:
        query = f"""
            WITH staff_emails AS (
                SELECT LOWER(Email_Address) as email
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
                WHERE Supervisor_Name__Unsecured_ = @supervisor_name
                AND Employment_Status IN ('Active', 'Leave of absence')
            ),
            meetings_with_staff AS (
                SELECT
                    m._id,
                    m.title,
                    m.date,
                    m.creator_name,
                    m.creator_email,
                    m.participant_names,
                    m.participant_emails,
                    m.type_name,
                    m.what_was_discussed,
                    m.next_steps,
                    m.created,
                    LOWER(TRIM(pe)) as staff_email
                FROM `{PROJECT_ID}.{DATASET_ID}.ldg_meetings` m,
                UNNEST(SPLIT(m.participant_emails, ', ')) as pe
                WHERE m.created >= '{CURRENT_SY_START}'
                AND m.archivedAt IS NULL
            )
            SELECT
                mws.*
            FROM meetings_with_staff mws
            INNER JOIN staff_emails se ON mws.staff_email = se.email
            ORDER BY mws.staff_email, mws.date DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("supervisor_name", "STRING", supervisor_name)
            ]
        )

        logger.info(f"Fetching meetings for supervisor: {supervisor_name}")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        meetings = {}
        for row in results:
            email = row.staff_email if row.staff_email else ''
            meeting = {
                'id': row._id,
                'title': row.title,
                'date': row.date.isoformat() if row.date else None,
                'creator_name': row.creator_name,
                'creator_email': row.creator_email,
                'participant_names': row.participant_names,
                'type_name': row.type_name,
                'what_was_discussed': row.what_was_discussed[:500] if row.what_was_discussed else None,
                'next_steps': row.next_steps[:500] if row.next_steps else None,
                'created': row.created.isoformat() if row.created else None
            }
            if email not in meetings:
                meetings[email] = []
            meetings[email].append(meeting)

        logger.info(f"Found meetings for {len(meetings)} staff members for {supervisor_name}")
        return jsonify(meetings)

    except Exception as e:
        logger.error(f"Error fetching meetings for {supervisor_name}: {e}")
        return jsonify({'error': str(e)}), 500
