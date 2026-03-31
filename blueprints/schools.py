"""Schools Dashboard routes."""

import os
import logging
from flask import Blueprint, jsonify, request, session
from google.cloud import bigquery

from config import PROJECT_ID, DATASET_ID, TABLE_ID, CURRENT_SY_START, PM_RESULTS_BY_TEST, PM_RESULTS_RAW, STUDENT_ROSTER, CLASS_SCHEDULES, SPS_BOTTOM_25
from extensions import bq_client
from auth import (
    login_required, get_schools_dashboard_role, compute_grade_band,
    map_grade_desc_to_levels, map_subject_desc_to_assessment,
)

logger = logging.getLogger(__name__)

bp = Blueprint('schools', __name__)

HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@bp.route('/schools-dashboard')
def schools_dashboard():
    """Serve the Schools Dashboard HTML file"""
    from app import serve_html
    return serve_html(os.path.join(HTML_DIR, 'schools-dashboard.html'))


@bp.route('/api/schools/staff', methods=['GET'])
@login_required
def get_schools_staff():
    """
    Get staff data for the Schools Dashboard.
    Role-based scoping: teachers_only or all_except_cteam.
    Excludes sensitive HR data (PMAP, ITR, IAP/Write-ups).
    Query params: location, supervisor, employee_type, job_function, subject, grade_band
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    schools_role = get_schools_dashboard_role(user_email)

    if not schools_role:
        return jsonify({'error': 'Access denied. Schools Dashboard access required.'}), 403

    scope = schools_role['scope']

    location_filter = request.args.get('location', '')
    supervisor_filter = request.args.get('supervisor', '')
    employee_type_filter = request.args.get('employee_type', '')
    job_function_filter = request.args.get('job_function', '')
    subject_filter = request.args.get('subject', '')
    grade_band_filter = request.args.get('grade_band', '')

    try:
        scope_filter = ""
        if scope == 'teachers_only':
            scope_filter = "AND s.Job_Function = 'Teacher'"
        elif scope == 'all_except_cteam':
            scope_filter = "AND sml.Job_Title NOT LIKE '%Chief%' AND sml.Job_Title NOT LIKE '%CEO%'"

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
            published_obs_counts AS (
                SELECT
                    teacher_internal_id,
                    COUNT(*) as total_published
                FROM (
                    SELECT DISTINCT
                        teacher_internal_id,
                        observation_type,
                        observed_at,
                        observer_name,
                        rubric_form
                    FROM `{PROJECT_ID}.{DATASET_ID}.observations_raw_native`
                    WHERE teacher_internal_id IS NOT NULL
                    AND is_published = 1
                    AND observed_at >= '{CURRENT_SY_START}'
                )
                GROUP BY teacher_internal_id
            )
            SELECT
                s.Employee_Number,
                s.first_name,
                s.last_name,
                s.Email_Address,
                FORMAT_DATE('%m-%d', s.Date_of_Birth) as birthday_month_day,
                s.Location_Name,
                s.Supervisor_Name__Unsecured_,
                s.job_title,
                s.Employment_Status,
                s.Last_Hire_Date,
                s.Job_Function,
                s.years_of_service,
                COALESCE(poc.total_published, 0) as total_observations,
                s.last_observation_date,
                s.last_observation_type,
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
                sml.Subject_Desc,
                sml.Grade_Level_Desc
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` s
            LEFT JOIN accrual_pivoted a ON s.Employee_Number = a.Person_Number
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(s.Email_Address) = LOWER(sml.Email_Address)
            LEFT JOIN published_obs_counts poc
                ON s.Employee_Number = CAST(poc.teacher_internal_id AS INT64)
            WHERE 1=1
                {scope_filter}
                {f"AND s.Location_Name = @location" if location_filter else ""}
                {f"AND s.Supervisor_Name__Unsecured_ = @supervisor" if supervisor_filter else ""}
                {f"AND sml.Salary_or_Hourly = @employee_type" if employee_type_filter else ""}
                {f"AND s.Job_Function = @job_function" if job_function_filter else ""}
                {f"AND sml.Subject_Desc = @subject" if subject_filter else ""}
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
        if subject_filter:
            params.append(bigquery.ScalarQueryParameter("subject", "STRING", subject_filter))

        job_config = bigquery.QueryJobConfig(query_parameters=params)

        logger.info(f"Schools Dashboard: Fetching staff data with scope={scope}")
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        staff_data = []
        for row in results:
            staff_member = dict(row.items())

            grade_level_desc = staff_member.get('Grade_Level_Desc', '')
            staff_member['grade_band'] = compute_grade_band(grade_level_desc)

            for key, value in staff_member.items():
                if hasattr(value, 'isoformat'):
                    staff_member[key] = value.isoformat()

            staff_data.append(staff_member)

        if grade_band_filter:
            staff_data = [s for s in staff_data if s.get('grade_band') == grade_band_filter]

        logger.info(f"Schools Dashboard: Found {len(staff_data)} staff members")
        return jsonify(staff_data)

    except Exception as e:
        logger.error(f"Error fetching schools staff: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/schools/filter-options', methods=['GET'])
@login_required
def get_schools_filter_options():
    """
    Get available filter options for the Schools Dashboard.
    Returns distinct values scoped by the user's role.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    schools_role = get_schools_dashboard_role(user_email)

    if not schools_role:
        return jsonify({'error': 'Access denied. Schools Dashboard access required.'}), 403

    scope = schools_role['scope']

    try:
        scope_filter = ""
        if scope == 'teachers_only':
            scope_filter = "AND s.Job_Function = 'Teacher'"
        elif scope == 'all_except_cteam':
            scope_filter = "AND sml.Job_Title NOT LIKE '%Chief%' AND sml.Job_Title NOT LIKE '%CEO%'"

        query = f"""
            SELECT DISTINCT
                s.Location_Name,
                s.Supervisor_Name__Unsecured_,
                sml.Salary_or_Hourly,
                s.Job_Function,
                sml.Subject_Desc,
                sml.Grade_Level_Desc
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}` s
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(s.Email_Address) = LOWER(sml.Email_Address)
            WHERE s.Location_Name IS NOT NULL
                {scope_filter}
        """

        results = bq_client.query(query).result()

        locations = set()
        supervisors = set()
        employee_types = set()
        job_functions = set()
        subjects = set()
        grade_bands = set()

        for row in results:
            if row.Location_Name:
                locations.add(row.Location_Name)
            if row.Supervisor_Name__Unsecured_:
                supervisors.add(row.Supervisor_Name__Unsecured_)
            if row.Salary_or_Hourly:
                employee_types.add(row.Salary_or_Hourly)
            if row.Job_Function:
                job_functions.add(row.Job_Function)
            if row.Subject_Desc:
                subjects.add(row.Subject_Desc)
            if row.Grade_Level_Desc:
                band = compute_grade_band(row.Grade_Level_Desc)
                if band:
                    grade_bands.add(band)

        return jsonify({
            'locations': sorted(list(locations)),
            'supervisors': sorted(list(supervisors)),
            'employee_types': sorted(list(employee_types)),
            'job_functions': sorted(list(job_functions)),
            'subjects': sorted(list(subjects)),
            'grade_bands': sorted(list(grade_bands))
        })

    except Exception as e:
        logger.error(f"Error fetching schools filter options: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/schools/action-steps', methods=['GET'])
@login_required
def get_schools_action_steps():
    """
    Get action steps for staff in the Schools Dashboard scope.
    Returns a dict of email -> action step info.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    schools_role = get_schools_dashboard_role(user_email)

    if not schools_role:
        return jsonify({'error': 'Access denied. Schools Dashboard access required.'}), 403

    scope = schools_role['scope']

    try:
        scope_filter = ""
        if scope == 'teachers_only':
            scope_filter = "AND s.Job_Function = 'Teacher'"
        elif scope == 'all_except_cteam':
            scope_filter = "AND s.Job_Title NOT LIKE '%Chief%' AND s.Job_Title NOT LIKE '%CEO%'"

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
            {scope_filter}
            ORDER BY a.user_email, a.created DESC
        """

        logger.info("Schools Dashboard: Fetching action steps")
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

        logger.info(f"Schools Dashboard: Found action steps for {len(action_steps)} staff members")
        return jsonify(action_steps)

    except Exception as e:
        logger.error(f"Error fetching schools action steps: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/schools/assessment-fidelity', methods=['GET'])
@login_required
def get_assessment_fidelity():
    """
    Get assessment fidelity data (completion % and mastery %) for the Schools Dashboard.
    Returns school-level summary and per-teacher data keyed by email.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    schools_role = get_schools_dashboard_role(user_email)

    if not schools_role:
        return jsonify({'error': 'Access denied. Schools Dashboard access required.'}), 403

    # Map staff Location_Name (full) → assessment School_Name (short)
    LOCATION_TO_SCHOOL = {
        'Arthur Ashe Charter School': 'Ashe',
        'Langston Hughes Academy': 'LHA',
        'Phillis Wheatley Community School': 'Wheatley',
        'Samuel J Green Charter School': 'Green',
    }
    # Reverse for display: short → full
    SCHOOL_TO_LOCATION = {v: k for k, v in LOCATION_TO_SCHOOL.items()}

    try:
        # Query 1 — School-level summary (most recent formal test per school)
        school_query = f"""
            WITH formal_tests AS (
                SELECT DISTINCT Test_ID
                FROM `{PM_RESULTS_RAW}`
                WHERE Assessment_Category NOT IN ('Quiz', 'Reading Checkpoint')
            ),
            school_metrics AS (
                SELECT
                    t.School_Name,
                    t.Test_Name,
                    t.Earliest_Test_Date,
                    t.Metric_Key,
                    AVG(t.Value) as avg_value,
                    DENSE_RANK() OVER (
                        PARTITION BY t.School_Name
                        ORDER BY t.Earliest_Test_Date DESC, t.Test_Name DESC
                    ) as test_rank
                FROM `{PM_RESULTS_BY_TEST}` t
                INNER JOIN formal_tests ft ON t.Test_ID = ft.Test_ID
                WHERE t.Metric_Key IN ('completion_percent', 'percent_scoring_75_or_above')
                AND t.Earliest_Test_Date >= '{CURRENT_SY_START}'
                AND t.School_Name != 'FLS'
                GROUP BY t.School_Name, t.Test_Name, t.Earliest_Test_Date, t.Metric_Key
            )
            SELECT * FROM school_metrics WHERE test_rank <= 2
        """

        # Query 2 — Teacher-level metrics from class_schedules + results_raw
        # Instead of school-wide aggregates from results_by_test, compute
        # per-teacher completion and mastery from actual class rosters.
        teacher_metrics_query = f"""
            WITH formal_tests AS (
                SELECT DISTINCT Test_ID
                FROM `{PM_RESULTS_RAW}`
                WHERE Assessment_Category NOT IN ('Quiz', 'Reading Checkpoint')
            ),
            recent_tests AS (
                SELECT DISTINCT
                    t.Test_ID,
                    t.Test_Name,
                    t.Earliest_Test_Date,
                    t.School_Name,
                    t.Grade_Level_of_Test,
                    t.Subject
                FROM `{PM_RESULTS_BY_TEST}` t
                INNER JOIN formal_tests ft ON t.Test_ID = ft.Test_ID
                WHERE t.Metric_Key = 'completion_percent'
                AND t.Earliest_Test_Date >= '{CURRENT_SY_START}'
                AND t.School_Name != 'FLS'
                QUALIFY DENSE_RANK() OVER (
                    PARTITION BY t.School_Name, t.Grade_Level_of_Test, t.Subject
                    ORDER BY t.Earliest_Test_Date DESC
                ) <= 2
            ),
            -- Regular teacher rosters from class_schedules
            direct_roster AS (
                SELECT DISTINCT
                    LOWER(cs.Teacher_Email) as teacher_email,
                    cs.Student_Number
                FROM `{CLASS_SCHEDULES}` cs
                WHERE cs.School_Year = 2025
                AND cs.Current_Enroll_Status = '0'
                AND cs.Teacher_Email IS NOT NULL
            ),
            -- SPED co-teacher virtual rosters: for each school/course,
            -- find the section with the most SPED students (inclusion section)
            sped_inclusion_sections AS (
                SELECT
                    cs.CC_School,
                    cs.Course_Number,
                    cs.Section_Number,
                    cs.Section_Grade_Level,
                    ROW_NUMBER() OVER (
                        PARTITION BY cs.CC_School, cs.Course_Number
                        ORDER BY COUNTIF(sr.SPEDIndicator = 'Yes') DESC
                    ) as sped_rank
                FROM `{CLASS_SCHEDULES}` cs
                LEFT JOIN `{STUDENT_ROSTER}` sr
                    ON cs.Student_Number = sr.Student_Number AND sr.Enroll_Status = 0
                WHERE cs.School_Year = 2025
                AND cs.Current_Enroll_Status = '0'
                AND cs.Section_Grade_Level BETWEEN 3 AND 8
                AND (cs.Course_Number LIKE 'MAT%' OR cs.Course_Number LIKE 'ELA%')
                GROUP BY cs.CC_School, cs.Course_Number, cs.Section_Number, cs.Section_Grade_Level
                HAVING COUNTIF(sr.SPEDIndicator = 'Yes') > 0
            ),
            -- Get all students in those inclusion sections
            sped_section_students AS (
                SELECT DISTINCT
                    cs.CC_School,
                    cs.Course_Number,
                    cs.Section_Grade_Level,
                    cs.Student_Number
                FROM `{CLASS_SCHEDULES}` cs
                INNER JOIN sped_inclusion_sections sis
                    ON cs.CC_School = sis.CC_School
                    AND cs.Course_Number = sis.Course_Number
                    AND cs.Section_Number = sis.Section_Number
                WHERE sis.sped_rank = 1
                AND cs.School_Year = 2025
                AND cs.Current_Enroll_Status = '0'
            ),
            -- SPED teachers who have no direct roster (co-teachers)
            -- Expand each teacher's Grade_Level_Desc into individual grade rows
            sped_teachers_raw AS (
                SELECT
                    LOWER(sml.Email_Address) as teacher_email,
                    sml.Location_Name,
                    sml.Grade_Level_Desc,
                    sml.Subject_Desc
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                LEFT JOIN direct_roster dr ON LOWER(sml.Email_Address) = dr.teacher_email
                WHERE sml.Job_Function = 'Teacher'
                AND LOWER(sml.job_title) LIKE '%sped%'
                AND sml.Employment_Status IN ('Active', 'Leave of absence')
                AND sml.Email_Address IS NOT NULL
                AND dr.teacher_email IS NULL
            ),
            sped_teachers_expanded AS (
                SELECT
                    st.teacher_email,
                    CASE st.Location_Name
                        WHEN 'Arthur Ashe Charter School' THEN 'Ashe'
                        WHEN 'Langston Hughes Academy' THEN 'LHA'
                        WHEN 'Phillis Wheatley Community School' THEN 'Wheatley'
                        WHEN 'Samuel J Green Charter School' THEN 'Green'
                    END as school_short,
                    st.Subject_Desc,
                    gl as grade_level
                FROM sped_teachers_raw st,
                UNNEST(
                    CASE
                        WHEN st.Grade_Level_Desc = '3&4' THEN [3, 4]
                        WHEN st.Grade_Level_Desc = '5&6' THEN [5, 6]
                        WHEN st.Grade_Level_Desc = '5&7' THEN [5, 7]
                        WHEN st.Grade_Level_Desc = '7&8' THEN [7, 8]
                        WHEN st.Grade_Level_Desc = '3 thru 5' THEN [3, 4, 5]
                        WHEN st.Grade_Level_Desc = '6 thru 8' THEN [6, 7, 8]
                        WHEN st.Grade_Level_Desc = '3' THEN [3]
                        WHEN st.Grade_Level_Desc = '4' THEN [4]
                        WHEN st.Grade_Level_Desc = '5' THEN [5]
                        WHEN st.Grade_Level_Desc = '6' THEN [6]
                        WHEN st.Grade_Level_Desc = '7' THEN [7]
                        WHEN st.Grade_Level_Desc = '8' THEN [8]
                        ELSE []
                    END
                ) as gl
            ),
            -- Map SPED teachers to inclusion section students
            -- Match by school + subject prefix + expanded grade level
            sped_virtual_roster AS (
                SELECT DISTINCT
                    ste.teacher_email,
                    sss.Student_Number
                FROM sped_teachers_expanded ste
                INNER JOIN sped_section_students sss
                    ON sss.CC_School = ste.school_short
                    AND sss.Section_Grade_Level = ste.grade_level
                    AND (
                        (ste.Subject_Desc = 'Math' AND sss.Course_Number LIKE 'MAT%')
                        OR (ste.Subject_Desc = 'ELA' AND sss.Course_Number LIKE 'ELA%')
                    )
            ),
            -- Combined roster: direct + SPED virtual
            roster AS (
                SELECT teacher_email, Student_Number FROM direct_roster
                UNION DISTINCT
                SELECT teacher_email, Student_Number FROM sped_virtual_roster
            ),
            student_results AS (
                SELECT
                    rr.Student_Number,
                    rr.Test_ID,
                    rr.Overall_Test_Score
                FROM `{PM_RESULTS_RAW}` rr
                INNER JOIN recent_tests rt ON rr.Test_ID = rt.Test_ID
            ),
            teacher_test_links AS (
                SELECT DISTINCT
                    r.teacher_email,
                    sr.Test_ID
                FROM roster r
                INNER JOIN student_results sr ON r.Student_Number = sr.Student_Number
            )
            SELECT
                ttl.teacher_email,
                rt.Test_Name,
                rt.Earliest_Test_Date,
                rt.School_Name,
                rt.Grade_Level_of_Test,
                rt.Subject,
                COUNT(DISTINCT r.Student_Number) as total_students,
                COUNT(DISTINCT sr.Student_Number) as tested_students,
                ROUND(SAFE_DIVIDE(COUNT(DISTINCT sr.Student_Number), COUNT(DISTINCT r.Student_Number)), 4) as completion_pct,
                ROUND(SAFE_DIVIDE(
                    COUNT(DISTINCT CASE WHEN sr.Overall_Test_Score >= 75 THEN sr.Student_Number END),
                    NULLIF(COUNT(DISTINCT sr.Student_Number), 0)
                ), 4) as mastery_pct
            FROM teacher_test_links ttl
            INNER JOIN roster r ON ttl.teacher_email = r.teacher_email
            INNER JOIN recent_tests rt ON ttl.Test_ID = rt.Test_ID
            LEFT JOIN student_results sr ON r.Student_Number = sr.Student_Number AND rt.Test_ID = sr.Test_ID
            GROUP BY ttl.teacher_email, rt.Test_Name, rt.Earliest_Test_Date, rt.School_Name, rt.Grade_Level_of_Test, rt.Subject
        """

        # Query 3 — Staff info for teacher matching
        staff_query = f"""
            SELECT
                Email_Address,
                Location_Name,
                Grade_Level_Desc,
                Subject_Desc,
                Job_Function
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE Employment_Status IN ('Active', 'Leave of absence')
            AND Email_Address IS NOT NULL
        """

        logger.info("Assessment fidelity: Running school summary query")
        school_results = list(bq_client.query(school_query).result())

        logger.info("Assessment fidelity: Running teacher metrics query")
        teacher_metrics_results = list(bq_client.query(teacher_metrics_query).result())

        logger.info("Assessment fidelity: Running staff query")
        staff_results = list(bq_client.query(staff_query).result())

        logger.info(f"Assessment fidelity: Got {len(school_results)} school rows, {len(teacher_metrics_results)} teacher metric rows, {len(staff_results)} staff rows")

        # ── Process school-level summary ──
        # Group by school → date_rank → metrics
        # Values are decimals (0.92 = 92%), multiply by 100 for display
        school_grouped = {}
        for row in school_results:
            loc = row.School_Name
            rank = row.test_rank
            if loc not in school_grouped:
                school_grouped[loc] = {}
            if rank not in school_grouped[loc]:
                school_grouped[loc][rank] = {
                    'test_name': row.Test_Name,
                    'test_date': row.Earliest_Test_Date.isoformat() if row.Earliest_Test_Date else None,
                    'completion_pct': None,
                    'mastery_pct': None,
                }
            entry = school_grouped[loc][rank]
            if row.Metric_Key == 'completion_percent':
                entry['completion_pct'] = round(row.avg_value * 100, 1) if row.avg_value is not None else None
            elif row.Metric_Key == 'percent_scoring_75_or_above':
                entry['mastery_pct'] = round(row.avg_value * 100, 1) if row.avg_value is not None else None

        school_summary = {}
        for loc, ranks in school_grouped.items():
            # Use full school name for display
            display_name = SCHOOL_TO_LOCATION.get(loc, loc)
            school_summary[display_name] = {}
            if 1 in ranks:
                school_summary[display_name]['current'] = ranks[1]
            if 2 in ranks:
                school_summary[display_name]['previous'] = ranks[2]

        # ── Build teacher metrics lookup from roster-based query ──
        # Key by teacher_email → list of test results
        teacher_metrics_lookup = {}
        for row in teacher_metrics_results:
            email = row.teacher_email
            if email not in teacher_metrics_lookup:
                teacher_metrics_lookup[email] = []
            teacher_metrics_lookup[email].append({
                'test_name': row.Test_Name,
                'test_date': row.Earliest_Test_Date.isoformat() if row.Earliest_Test_Date else None,
                'school': row.School_Name,
                'grade': row.Grade_Level_of_Test,
                'subject': row.Subject,
                'completion_pct': round(row.completion_pct * 100, 1) if row.completion_pct is not None else None,
                'mastery_pct': round(row.mastery_pct * 100, 1) if row.mastery_pct is not None else None,
            })

        # ── Match teachers to assessment data ──
        # Use staff Grade_Level_Desc and Subject_Desc to filter which tests
        # are relevant, then use roster-based metrics (not school-wide aggregates)
        teacher_data = {}
        for staff_row in staff_results:
            email = (staff_row.Email_Address or '').lower()
            if not email:
                continue

            if staff_row.Job_Function != 'Teacher':
                continue

            # Map staff Location_Name to assessment School_Name
            school_short = LOCATION_TO_SCHOOL.get(staff_row.Location_Name)
            if not school_short:
                continue

            grade_levels = map_grade_desc_to_levels(staff_row.Grade_Level_Desc)
            subjects = map_subject_desc_to_assessment(staff_row.Subject_Desc)

            # Get this teacher's roster-based metrics
            metrics = teacher_metrics_lookup.get(email, [])

            # Filter by school, grade, subject
            matching = []
            for m in metrics:
                if m['school'] != school_short:
                    continue
                if grade_levels is not None and m['grade'] not in grade_levels:
                    continue
                if subjects is not None and m['subject'] not in subjects:
                    continue
                matching.append(m)

            if not matching:
                continue

            # Sort by date descending, deduplicate by test_name, pick top 2
            matching.sort(key=lambda t: t['test_date'] or '', reverse=True)
            seen_tests = set()
            unique_tests = []
            for t in matching:
                if t['test_name'] not in seen_tests:
                    seen_tests.add(t['test_name'])
                    unique_tests.append(t)

            if unique_tests:
                teacher_data[email] = {
                    'current': {
                        'test_name': unique_tests[0]['test_name'],
                        'test_date': unique_tests[0]['test_date'],
                        'completion_pct': unique_tests[0]['completion_pct'],
                        'mastery_pct': unique_tests[0]['mastery_pct'],
                    }
                }
                if len(unique_tests) > 1:
                    teacher_data[email]['previous'] = {
                        'test_name': unique_tests[1]['test_name'],
                        'test_date': unique_tests[1]['test_date'],
                        'completion_pct': unique_tests[1]['completion_pct'],
                        'mastery_pct': unique_tests[1]['mastery_pct'],
                    }

        logger.info(f"Assessment fidelity: {len(school_summary)} schools, {len(teacher_data)} teachers")
        return jsonify({
            'school_summary': school_summary,
            'teacher_data': teacher_data,
        })

    except Exception as e:
        logger.error(f"Error fetching assessment fidelity: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/schools/assessment-students', methods=['GET'])
@login_required
def get_assessment_students():
    """
    Get student-level data for a specific teacher + test.
    Uses class_schedules to find the teacher's students, then cross-references
    with results_raw to show who tested, scores, and who's missing.

    Query params: teacher_email, test_name
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    schools_role = get_schools_dashboard_role(user_email)

    if not schools_role:
        return jsonify({'error': 'Access denied. Schools Dashboard access required.'}), 403

    teacher_email = request.args.get('teacher_email', '').strip()
    test_name = request.args.get('test_name', '')  # Don't strip — test names may have trailing spaces in BQ

    if not teacher_email or not test_name:
        return jsonify({'error': 'teacher_email and test_name are required'}), 400

    try:
        # Get the teacher's rostered students from class_schedules (current year, enrolled)
        # For SPED co-teachers with no direct roster, use the SPED inclusion section
        # (section with the most SPED students) at their school/grade/subject.
        # Then left join with results_raw to see who tested and their scores.
        # Also left join with SPS bottom 25th percentile table to flag priority students.
        query = f"""
            WITH direct_students AS (
                SELECT DISTINCT
                    cs.Student_Number,
                    cs.First_Name,
                    cs.Last_Name,
                    cs.Current_Grade_Level
                FROM `{CLASS_SCHEDULES}` cs
                WHERE cs.School_Year = 2025
                AND LOWER(cs.Teacher_Email) = LOWER(@teacher_email)
                AND cs.Current_Enroll_Status = '0'
            ),
            -- SPED co-teacher fallback: find their inclusion section students
            sped_teacher_info AS (
                SELECT
                    sml.Location_Name,
                    sml.Grade_Level_Desc,
                    sml.Subject_Desc
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                WHERE LOWER(sml.Email_Address) = LOWER(@teacher_email)
                AND LOWER(sml.job_title) LIKE '%sped%'
                AND sml.Job_Function = 'Teacher'
                LIMIT 1
            ),
            sped_inclusion_sections AS (
                SELECT
                    cs.CC_School,
                    cs.Course_Number,
                    cs.Section_Number,
                    cs.Section_Grade_Level,
                    ROW_NUMBER() OVER (
                        PARTITION BY cs.CC_School, cs.Course_Number
                        ORDER BY COUNTIF(sr.SPEDIndicator = 'Yes') DESC
                    ) as sped_rank
                FROM `{CLASS_SCHEDULES}` cs
                LEFT JOIN `{STUDENT_ROSTER}` sr
                    ON cs.Student_Number = sr.Student_Number AND sr.Enroll_Status = 0
                WHERE cs.School_Year = 2025
                AND cs.Current_Enroll_Status = '0'
                AND cs.Section_Grade_Level BETWEEN 3 AND 8
                AND (cs.Course_Number LIKE 'MAT%' OR cs.Course_Number LIKE 'ELA%')
                GROUP BY cs.CC_School, cs.Course_Number, cs.Section_Number, cs.Section_Grade_Level
                HAVING COUNTIF(sr.SPEDIndicator = 'Yes') > 0
            ),
            -- Expand SPED teacher grade levels into individual rows
            sped_teacher_grades AS (
                SELECT
                    sti.Location_Name,
                    sti.Subject_Desc,
                    gl as grade_level,
                    CASE sti.Location_Name
                        WHEN 'Arthur Ashe Charter School' THEN 'Ashe'
                        WHEN 'Langston Hughes Academy' THEN 'LHA'
                        WHEN 'Phillis Wheatley Community School' THEN 'Wheatley'
                        WHEN 'Samuel J Green Charter School' THEN 'Green'
                    END as school_short
                FROM sped_teacher_info sti,
                UNNEST(
                    CASE
                        WHEN sti.Grade_Level_Desc = '3&4' THEN [3, 4]
                        WHEN sti.Grade_Level_Desc = '5&6' THEN [5, 6]
                        WHEN sti.Grade_Level_Desc = '5&7' THEN [5, 7]
                        WHEN sti.Grade_Level_Desc = '7&8' THEN [7, 8]
                        WHEN sti.Grade_Level_Desc = '3 thru 5' THEN [3, 4, 5]
                        WHEN sti.Grade_Level_Desc = '6 thru 8' THEN [6, 7, 8]
                        WHEN sti.Grade_Level_Desc = '3' THEN [3]
                        WHEN sti.Grade_Level_Desc = '4' THEN [4]
                        WHEN sti.Grade_Level_Desc = '5' THEN [5]
                        WHEN sti.Grade_Level_Desc = '6' THEN [6]
                        WHEN sti.Grade_Level_Desc = '7' THEN [7]
                        WHEN sti.Grade_Level_Desc = '8' THEN [8]
                        ELSE []
                    END
                ) as gl
            ),
            sped_virtual_students AS (
                SELECT DISTINCT
                    cs.Student_Number,
                    cs.First_Name,
                    cs.Last_Name,
                    cs.Current_Grade_Level
                FROM sped_teacher_grades stg
                INNER JOIN sped_inclusion_sections sis
                    ON sis.CC_School = stg.school_short
                    AND sis.Section_Grade_Level = stg.grade_level
                    AND (
                        (stg.Subject_Desc = 'Math' AND sis.Course_Number LIKE 'MAT%')
                        OR (stg.Subject_Desc = 'ELA' AND sis.Course_Number LIKE 'ELA%')
                    )
                INNER JOIN `{CLASS_SCHEDULES}` cs
                    ON cs.CC_School = sis.CC_School
                    AND cs.Course_Number = sis.Course_Number
                    AND cs.Section_Number = sis.Section_Number
                WHERE sis.sped_rank = 1
                AND cs.School_Year = 2025
                AND cs.Current_Enroll_Status = '0'
            ),
            -- Combine direct roster with SPED virtual roster
            -- For regular teachers: direct_students has data, sped_virtual is empty
            -- For SPED co-teachers: direct_students is empty, sped_virtual has data
            all_teacher_students AS (
                SELECT * FROM direct_students
                UNION DISTINCT
                SELECT * FROM sped_virtual_students
            ),
            -- Determine the test's target grade level to filter students
            test_grade AS (
                SELECT DISTINCT Grade_Level_of_Test as grade
                FROM `{PM_RESULTS_BY_TEST}`
                WHERE TRIM(Test_Name) = TRIM(@test_name)
                LIMIT 1
            ),
            -- Filter students to only those matching the test's grade
            -- (prevents showing 8th graders for a 7th grade test, etc.)
            teacher_students AS (
                SELECT ts.*
                FROM all_teacher_students ts
                LEFT JOIN test_grade tg ON TRUE
                WHERE tg.grade IS NULL
                   OR ts.Current_Grade_Level = tg.grade
            ),
            test_results AS (
                SELECT DISTINCT
                    r.Student_Number,
                    r.Overall_Test_Score,
                    r.Overall_Test_Points_Earned,
                    r.Overall_Test_Points_Possible
                FROM `{PM_RESULTS_RAW}` r
                WHERE TRIM(r.Test_Name) = TRIM(@test_name)
            )
            SELECT
                ts.Student_Number,
                ts.First_Name,
                ts.Last_Name,
                ts.Current_Grade_Level,
                tr.Overall_Test_Score,
                tr.Overall_Test_Points_Earned,
                tr.Overall_Test_Points_Possible,
                CASE WHEN tr.Student_Number IS NOT NULL THEN TRUE ELSE FALSE END as tested,
                CASE WHEN b25.Bottom_25th = 'Yes' THEN TRUE ELSE FALSE END as bottom_25,
                b25.ELA_25th,
                b25.Math_25th
            FROM teacher_students ts
            LEFT JOIN test_results tr ON ts.Student_Number = tr.Student_Number
            LEFT JOIN `{SPS_BOTTOM_25}` b25 ON CAST(ts.Student_Number AS STRING) = b25.Student_Number
            ORDER BY tested ASC, ts.Last_Name, ts.First_Name
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("teacher_email", "STRING", teacher_email),
                bigquery.ScalarQueryParameter("test_name", "STRING", test_name),
            ]
        )

        logger.info(f"Assessment students: teacher={teacher_email}, test={test_name}")
        results = list(bq_client.query(query, job_config=job_config).result())

        students = []
        tested_count = 0
        missing_count = 0

        for row in results:
            student = {
                'student_number': row.Student_Number,
                'first_name': row.First_Name,
                'last_name': row.Last_Name,
                'grade_level': row.Current_Grade_Level,
                'tested': row.tested,
                'score': round(row.Overall_Test_Score, 1) if row.Overall_Test_Score is not None else None,
                'points_earned': row.Overall_Test_Points_Earned,
                'points_possible': row.Overall_Test_Points_Possible,
                'bottom_25': row.bottom_25,
                'ela_25th': row.ELA_25th == 'Yes' if row.ELA_25th else False,
                'math_25th': row.Math_25th == 'Yes' if row.Math_25th else False,
            }
            if row.tested:
                tested_count += 1
            else:
                missing_count += 1
            students.append(student)

        logger.info(f"Assessment students: {tested_count} tested, {missing_count} missing")
        return jsonify({
            'students': students,
            'tested_count': tested_count,
            'missing_count': missing_count,
            'total_count': len(students),
            'test_name': test_name,
            'teacher_email': teacher_email,
        })

    except Exception as e:
        logger.error(f"Error fetching assessment students: {e}")
        return jsonify({'error': str(e)}), 500
