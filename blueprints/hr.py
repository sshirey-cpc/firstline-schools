"""HR/Talent Dashboard routes."""

import os
import logging
from flask import Blueprint, jsonify, request, session, send_from_directory
from google.cloud import bigquery

from config import PROJECT_ID, DATASET_ID, TABLE_ID, CURRENT_SY_START
from extensions import bq_client
from auth import login_required, is_hr_admin

logger = logging.getLogger(__name__)

bp = Blueprint('hr', __name__)

HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@bp.route('/hr-dashboard')
def hr_dashboard():
    """Serve the HR/Talent dashboard HTML file"""
    return send_from_directory(HTML_DIR, 'hr-dashboard.html')


@bp.route('/api/all-staff', methods=['GET'])
@login_required
def get_all_staff():
    """
    Get all staff members with optional filters.
    Only accessible by admin users.
    Query params:
        - location: Filter by location name
        - supervisor: Filter by supervisor name
        - employee_type: Filter by Salary_or_Hourly (Salary, Hourly)
        - job_function: Filter by Job_Function
    Returns: JSON array of staff records with all fields
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()

    if not is_hr_admin(user_email):
        logger.warning(f"Authorization denied: user {user_email} tried to access all-staff (not HR admin)")
        return jsonify({'error': 'Access denied. Admin access required.'}), 403

    location_filter = request.args.get('location', '')
    supervisor_filter = request.args.get('supervisor', '')
    employee_type_filter = request.args.get('employee_type', '')
    job_function_filter = request.args.get('job_function', '')

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
                    (COUNTIF(is_self_pmap AND form_round = 1) > 0
                        AND COUNTIF(is_self AND form_round = 1 AND NOT is_self_pmap) = 0) as sr1_wrong_form,
                    (COUNTIF(is_self_pmap AND form_round = 2) > 0
                        AND COUNTIF(is_self AND form_round = 2 AND NOT is_self_pmap) = 0) as sr2_wrong_form,
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
                s.last_observation_date,
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
                s.last_observation_type,
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
            WHERE 1=1
                {f"AND s.Location_Name = @location" if location_filter else ""}
                {f"AND s.Supervisor_Name__Unsecured_ = @supervisor" if supervisor_filter else ""}
                {f"AND sml.Salary_or_Hourly = @employee_type" if employee_type_filter else ""}
                {f"AND s.Job_Function = @job_function" if job_function_filter else ""}
            ORDER BY s.Location_Name, s.last_name, s.first_name
        """

        params = []
        if location_filter:
            params.append(bigquery.ScalarQueryParameter("location", "STRING", location_filter))
        if supervisor_filter:
            params.append(bigquery.ScalarQueryParameter("supervisor", "STRING", supervisor_filter))
        if employee_type_filter:
            params.append(bigquery.ScalarQueryParameter("employee_type", "STRING", employee_type_filter))
        if job_function_filter:
            params.append(bigquery.ScalarQueryParameter("job_function", "STRING", job_function_filter))

        job_config = bigquery.QueryJobConfig(query_parameters=params)

        logger.info(f"Fetching all staff data with filters: location={location_filter}, supervisor={supervisor_filter}, employee_type={employee_type_filter}, job_function={job_function_filter}")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        staff_data = []
        for row in results:
            staff_member = dict(row.items())
            for key, value in staff_member.items():
                if hasattr(value, 'isoformat'):
                    staff_member[key] = value.isoformat()
            staff_data.append(staff_member)

        logger.info(f"Found {len(staff_data)} staff members")
        return jsonify(staff_data)

    except Exception as e:
        logger.error(f"Error fetching all staff: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/filter-options', methods=['GET'])
@login_required
def get_filter_options():
    """
    Get available filter options for the HR/Talent dashboard.
    Returns distinct values for locations, supervisors, employee types, and job functions.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()

    if not is_hr_admin(user_email):
        return jsonify({'error': 'Access denied. Admin access required.'}), 403

    try:
        query = f"""
            SELECT DISTINCT
                s.Location_Name,
                s.Supervisor_Name__Unsecured_,
                sml.Salary_or_Hourly,
                s.Job_Function
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` s
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(s.Email_Address) = LOWER(sml.Email_Address)
            WHERE s.Location_Name IS NOT NULL
        """

        results = bq_client.query(query).result()

        locations = set()
        supervisors = set()
        employee_types = set()
        job_functions = set()

        for row in results:
            if row.Location_Name:
                locations.add(row.Location_Name)
            if row.Supervisor_Name__Unsecured_:
                supervisors.add(row.Supervisor_Name__Unsecured_)
            if row.Salary_or_Hourly:
                employee_types.add(row.Salary_or_Hourly)
            if row.Job_Function:
                job_functions.add(row.Job_Function)

        return jsonify({
            'locations': sorted(list(locations)),
            'supervisors': sorted(list(supervisors)),
            'employee_types': sorted(list(employee_types)),
            'job_functions': sorted(list(job_functions))
        })

    except Exception as e:
        logger.error(f"Error fetching filter options: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/all-action-steps', methods=['GET'])
@login_required
def get_all_action_steps():
    """
    Get action steps for all staff members (admin only).
    Returns a dict of email -> action step info.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()

    if not is_hr_admin(user_email):
        return jsonify({'error': 'Access denied. Admin access required.'}), 403

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
            WHERE s.Employment_Status IN ('Active', 'Leave of absence')
            AND a.archivedAt IS NULL
            AND a.created >= '{CURRENT_SY_START}'
            ORDER BY a.user_email, a.created DESC
        """

        logger.info("Fetching all action steps for HR dashboard")
        query_job = bq_client.query(query)
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

        logger.info(f"Found action steps for {len(action_steps)} staff members")
        return jsonify(action_steps)

    except Exception as e:
        logger.error(f"Error fetching all action steps: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/pmap-network', methods=['GET'])
@login_required
def get_pmap_network():
    """Network-wide PMAP/SR completion data for all schools."""
    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    if not is_hr_admin(user_email):
        return jsonify({'error': 'HR admin access required'}), 403

    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            WITH classified_obs AS (
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
                    COUNTIF(is_self AND form_round = 1) as sr1,
                    COUNTIF(is_self AND form_round = 2) as sr2,
                    COUNTIF(NOT is_self AND form_round = 1
                            AND (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')) as pmap1,
                    COUNTIF(NOT is_self AND form_round = 2
                            AND (observation_type LIKE '%PMAP%' OR observation_type LIKE '%Self-Reflection%')) as pmap2,
                    (COUNTIF(is_self_pmap AND form_round = 1) > 0
                        AND COUNTIF(is_self AND form_round = 1 AND NOT is_self_pmap) = 0) as sr1_wrong_form,
                    (COUNTIF(is_self_pmap AND form_round = 2) > 0
                        AND COUNTIF(is_self AND form_round = 2 AND NOT is_self_pmap) = 0) as sr2_wrong_form,
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
            )
            SELECT
                s.Employee_Number,
                CONCAT(s.first_name, ' ', s.last_name) as staff_name,
                s.Location_Name as school,
                s.Supervisor_Name__Unsecured_ as supervisor,
                s.job_title,
                s.Job_Function,
                s.Employment_Status,
                s.Last_Hire_Date,
                sml.Salary_or_Hourly,
                COALESCE(poc.sr1, 0) as sr1,
                COALESCE(poc.sr2, 0) as sr2,
                COALESCE(poc.pmap1, 0) as pmap1,
                COALESCE(poc.pmap2, 0) as pmap2,
                COALESCE(poc.sr1_wrong_form, FALSE) as sr1_wrong_form,
                COALESCE(poc.sr2_wrong_form, FALSE) as sr2_wrong_form,
                COALESCE(poc.pmap1_wrong_form, FALSE) as pmap1_wrong_form,
                COALESCE(poc.pmap2_wrong_form, FALSE) as pmap2_wrong_form,
                COALESCE(poc.teacher_rubric_count, 0) as teacher_rubric_count,
                COALESCE(poc.teacher_form_sr1, FALSE) as teacher_form_sr1,
                COALESCE(poc.teacher_form_sr2, FALSE) as teacher_form_sr2,
                COALESCE(poc.teacher_form_pmap1, FALSE) as teacher_form_pmap1,
                COALESCE(poc.teacher_form_pmap2, FALSE) as teacher_form_pmap2
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` s
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(s.Email_Address) = LOWER(sml.Email_Address)
            LEFT JOIN published_obs_counts poc
                ON s.Employee_Number = CAST(poc.teacher_internal_id AS INT64)
            WHERE s.Employment_Status IN ('Active', 'Leave of absence')
            ORDER BY s.Location_Name, s.Supervisor_Name__Unsecured_, s.last_name
        """

        results = bq_client.query(query).result()
        staff_data = []
        for row in results:
            staff_member = dict(row.items())
            for key, value in staff_member.items():
                if hasattr(value, 'isoformat'):
                    staff_member[key] = value.isoformat()
            staff_data.append(staff_member)

        logger.info(f"PMAP network data: {len(staff_data)} staff members")
        return jsonify(staff_data)

    except Exception as e:
        logger.error(f"Error fetching PMAP network data: {e}")
        return jsonify({'error': str(e)}), 500
