"""Kickboard Dashboard routes."""

import os
import logging
from flask import Blueprint, jsonify, request, session
from google.cloud import bigquery

from config import (
    KICKBOARD_TABLE, KICKBOARD_ACL_TABLE, KICKBOARD_SCHOOL_MAP,
    CURRENT_SY_START, PROJECT_ID, DATASET_ID,
)
from extensions import bq_client, get_school_start_date
from auth import login_required, is_admin, get_kickboard_access, resolve_email_alias

logger = logging.getLogger(__name__)

bp = Blueprint('kickboard', __name__)

HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_table_and_access_condition(user_email, access):
    """
    Build table and access conditions based on hybrid access model.
    - Admin: no filter (see all)
    - School access: filter by school codes
    - Staff ID access: filter by UKG_Staff_ID
    - Hybrid: OR combination of school and staff filters

    Always includes current school-year date floor.
    Returns (table_name, base_conditions_list, base_params_list).
    """
    sy_cond = ["Interaction_Date >= @sy_start"]
    sy_param = [bigquery.ScalarQueryParameter("sy_start", "STRING", CURRENT_SY_START)]

    # Admin access - no additional filters
    if access.get('access_type') == 'admin':
        return KICKBOARD_TABLE, sy_cond, sy_param

    # Build access filter based on schools and/or staff_ids
    schools = access.get('schools', [])
    staff_ids = access.get('staff_ids', [])

    access_conditions = []

    if schools:
        # School-level access
        school_placeholders = ', '.join([f'@school_{i}' for i in range(len(schools))])
        access_conditions.append(f"School IN ({school_placeholders})")
        for i, school in enumerate(schools):
            sy_param.append(bigquery.ScalarQueryParameter(f"school_{i}", "STRING", school))

    if staff_ids:
        # Staff ID access (supervisor's downline)
        staff_placeholders = ', '.join([f'@staff_{i}' for i in range(len(staff_ids))])
        access_conditions.append(f"UKG_Staff_ID IN ({staff_placeholders})")
        for i, staff_id in enumerate(staff_ids):
            sy_param.append(bigquery.ScalarQueryParameter(f"staff_{i}", "STRING", staff_id))

    # Combine with OR if both exist
    if access_conditions:
        combined = f"({' OR '.join(access_conditions)})"
        sy_cond.append(combined)

    return KICKBOARD_TABLE, sy_cond, sy_param


@bp.route('/kickboard-dashboard')
def kickboard_dashboard():
    """Serve the Kickboard Dashboard HTML file"""
    from app import serve_html
    return serve_html(os.path.join(HTML_DIR, 'kickboard-dashboard.html'))


@bp.route('/api/kickboard/summary', methods=['GET'])
@login_required
def kickboard_summary():
    """
    Network-level school summaries for the Kickboard dashboard.
    Returns per-school metrics and network totals.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied. Kickboard Dashboard access required.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)

    school = request.args.get('school', '')
    grade = request.args.get('grade', '')
    category = request.args.get('category', '')
    staff = request.args.get('staff', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conditions = ["Staff != 'System Administrator'"] + acl_conds
    params = list(acl_params)

    if school:
        conditions.append("School = @school")
        params.append(bigquery.ScalarQueryParameter("school", "STRING", school))
    if grade:
        conditions.append("CAST(Grade_Level AS STRING) = @grade")
        params.append(bigquery.ScalarQueryParameter("grade", "STRING", str(grade)))
    if category:
        conditions.append("Category = @category")
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    if staff:
        conditions.append("Staff = @staff")
        params.append(bigquery.ScalarQueryParameter("staff", "STRING", staff))
    if date_from:
        conditions.append("Interaction_Date >= @date_from")
        params.append(bigquery.ScalarQueryParameter("date_from", "STRING", date_from))
    if date_to:
        conditions.append("Interaction_Date <= @date_to")
        params.append(bigquery.ScalarQueryParameter("date_to", "STRING", date_to))

    where_clause = " AND ".join(conditions)

    # Deposit sub-query always uses the base interactions table (no ACL)
    deposit_conditions = ["Staff = 'System Administrator'", "Interaction_Date >= @sy_start"]
    if school:
        deposit_conditions.append("School = @school")
    if grade:
        deposit_conditions.append("CAST(Grade_Level AS STRING) = @grade")
    if category:
        deposit_conditions.append("Category = @category")
    if date_from:
        deposit_conditions.append("Interaction_Date >= @date_from")
    if date_to:
        deposit_conditions.append("Interaction_Date <= @date_to")
    deposit_where = " AND ".join(deposit_conditions)

    try:
        query = f"""
            WITH current_data AS (
                SELECT
                    School,
                    COUNT(*) as interactions,
                    COUNTIF(Dollar_Value > 0) as positive_count,
                    COUNTIF(Dollar_Value < 0) as negative_count,
                    SUM(CASE WHEN Dollar_Value > 0 THEN Dollar_Value ELSE 0 END) as total_earned,
                    SUM(CASE WHEN Dollar_Value < 0 THEN Dollar_Value ELSE 0 END) as total_lost,
                    COUNT(DISTINCT Student_Number) as unique_students,
                    COUNT(DISTINCT Staff) as unique_staff
                FROM `{table}`
                WHERE {where_clause}
                GROUP BY School
            ),
            weekly_data AS (
                SELECT
                    School,
                    COUNTIF(Interaction_Date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)) as this_week,
                    COUNTIF(Interaction_Date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY) AND Interaction_Date < DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)) as last_week
                FROM `{table}`
                WHERE {where_clause}
                GROUP BY School
            ),
            deposit_data AS (
                SELECT
                    School,
                    COUNT(*) as deposit_count
                FROM `{KICKBOARD_TABLE}`
                WHERE {deposit_where}
                AND School IN (SELECT School FROM current_data)
                GROUP BY School
            )
            SELECT
                c.School,
                c.interactions,
                c.positive_count,
                c.negative_count,
                c.total_earned,
                c.total_lost,
                c.unique_students,
                c.unique_staff,
                COALESCE(d.deposit_count, 0) as deposit_count,
                w.this_week,
                w.last_week,
                CASE
                    WHEN w.last_week > 0
                    THEN ROUND((w.this_week - w.last_week) * 100.0 / w.last_week, 1)
                    ELSE 0
                END as wow_trend
            FROM current_data c
            LEFT JOIN weekly_data w ON c.School = w.School
            LEFT JOIN deposit_data d ON c.School = d.School
            ORDER BY c.School
        """

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        schools = []
        network_totals = {
            'interactions': 0, 'positive_count': 0, 'negative_count': 0,
            'total_earned': 0, 'total_lost': 0, 'unique_students': 0,
            'unique_staff': 0, 'deposit_count': 0
        }

        for row in results:
            pos = row.positive_count or 0
            neg = row.negative_count or 0
            ratio = round(pos / neg, 2) if neg > 0 else pos
            school_data = {
                'school': row.School,
                'full_name': KICKBOARD_SCHOOL_MAP.get(row.School, row.School),
                'interactions': row.interactions or 0,
                'positive_count': pos,
                'negative_count': neg,
                'ratio': ratio,
                'total_earned': float(row.total_earned or 0),
                'total_lost': float(row.total_lost or 0),
                'unique_students': row.unique_students or 0,
                'unique_staff': row.unique_staff or 0,
                'deposit_count': row.deposit_count or 0,
                'wow_trend': float(row.wow_trend or 0),
                'this_week': row.this_week or 0,
                'last_week': row.last_week or 0
            }
            schools.append(school_data)

            for key in network_totals:
                network_totals[key] += school_data.get(key, 0)

        nt_pos = network_totals['positive_count']
        nt_neg = network_totals['negative_count']
        network_totals['ratio'] = round(nt_pos / nt_neg, 2) if nt_neg > 0 else nt_pos

        logger.info(f"Kickboard summary: {len(schools)} schools for {user_email}")
        return jsonify({'schools': schools, 'network_totals': network_totals})

    except Exception as e:
        logger.error(f"Error fetching kickboard summary: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/kickboard/grades', methods=['GET'])
@login_required
def kickboard_grades():
    """Grade breakdown for one school (drill-down level 1)."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)

    school = request.args.get('school', '')
    if not school:
        return jsonify({'error': 'School is required.'}), 400

    grade = request.args.get('grade', '')
    category = request.args.get('category', '')
    staff = request.args.get('staff', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conditions = ["School = @school", "Staff != 'System Administrator'"] + acl_conds
    params = [bigquery.ScalarQueryParameter("school", "STRING", school)] + list(acl_params)

    if grade:
        conditions.append("CAST(Grade_Level AS STRING) = @grade")
        params.append(bigquery.ScalarQueryParameter("grade", "STRING", str(grade)))
    if category:
        conditions.append("Category = @category")
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    if staff:
        conditions.append("Staff = @staff")
        params.append(bigquery.ScalarQueryParameter("staff", "STRING", staff))
    if date_from:
        conditions.append("Interaction_Date >= @date_from")
        params.append(bigquery.ScalarQueryParameter("date_from", "STRING", date_from))
    if date_to:
        conditions.append("Interaction_Date <= @date_to")
        params.append(bigquery.ScalarQueryParameter("date_to", "STRING", date_to))

    where_clause = " AND ".join(conditions)

    try:
        query = f"""
            SELECT
                Grade_Level,
                COUNT(*) as interactions,
                COUNTIF(Dollar_Value > 0) as positive_count,
                COUNTIF(Dollar_Value < 0) as negative_count,
                SUM(CASE WHEN Dollar_Value > 0 THEN Dollar_Value ELSE 0 END) as total_earned,
                SUM(CASE WHEN Dollar_Value < 0 THEN Dollar_Value ELSE 0 END) as total_lost,
                COUNT(DISTINCT Student_Number) as unique_students
            FROM `{table}`
            WHERE {where_clause}
            GROUP BY Grade_Level
            ORDER BY Grade_Level
        """

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        grades = []
        school_totals = {
            'interactions': 0, 'positive_count': 0, 'negative_count': 0,
            'total_earned': 0, 'total_lost': 0, 'unique_students': 0
        }

        for row in results:
            pos = row.positive_count or 0
            neg = row.negative_count or 0
            ratio = round(pos / neg, 2) if neg > 0 else pos
            grade_data = {
                'grade': row.Grade_Level,
                'interactions': row.interactions or 0,
                'positive_count': pos,
                'negative_count': neg,
                'ratio': ratio,
                'total_earned': float(row.total_earned or 0),
                'total_lost': float(row.total_lost or 0),
                'unique_students': row.unique_students or 0
            }
            grades.append(grade_data)

            for key in school_totals:
                school_totals[key] += grade_data.get(key, 0)

        nt_pos = school_totals['positive_count']
        nt_neg = school_totals['negative_count']
        school_totals['ratio'] = round(nt_pos / nt_neg, 2) if nt_neg > 0 else nt_pos

        logger.info(f"Kickboard grades: {len(grades)} grades for {school}")
        return jsonify({'grades': grades, 'school_totals': school_totals, 'school': school})

    except Exception as e:
        logger.error(f"Error fetching kickboard grades: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/kickboard/teachers', methods=['GET'])
@login_required
def kickboard_teachers():
    """Teacher breakdown for one school (drill-down level 1, alternative to grades)."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)

    school = request.args.get('school', '')
    if not school:
        return jsonify({'error': 'School is required.'}), 400

    grade = request.args.get('grade', '')
    category = request.args.get('category', '')
    staff_filter = request.args.get('staff', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conditions = ["School = @school", "Staff != 'System Administrator'"] + acl_conds
    params = [bigquery.ScalarQueryParameter("school", "STRING", school)] + list(acl_params)

    if grade:
        conditions.append("CAST(Grade_Level AS STRING) = @grade")
        params.append(bigquery.ScalarQueryParameter("grade", "STRING", str(grade)))
    if category:
        conditions.append("Category = @category")
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    if staff_filter:
        conditions.append("Staff = @staff")
        params.append(bigquery.ScalarQueryParameter("staff", "STRING", staff_filter))
    if date_from:
        conditions.append("Interaction_Date >= @date_from")
        params.append(bigquery.ScalarQueryParameter("date_from", "STRING", date_from))
    if date_to:
        conditions.append("Interaction_Date <= @date_to")
        params.append(bigquery.ScalarQueryParameter("date_to", "STRING", date_to))

    where_clause = " AND ".join(conditions)

    try:
        query = f"""
            SELECT
                Staff,
                COUNT(*) as interactions,
                COUNTIF(Dollar_Value > 0) as positive_count,
                COUNTIF(Dollar_Value < 0) as negative_count,
                SUM(CASE WHEN Dollar_Value > 0 THEN Dollar_Value ELSE 0 END) as total_earned,
                SUM(CASE WHEN Dollar_Value < 0 THEN Dollar_Value ELSE 0 END) as total_lost,
                COUNT(DISTINCT Student_Number) as unique_students
            FROM `{table}`
            WHERE {where_clause}
            GROUP BY Staff
            ORDER BY Staff
        """

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        teachers = []
        school_totals = {
            'interactions': 0, 'positive_count': 0, 'negative_count': 0,
            'total_earned': 0, 'total_lost': 0, 'unique_students': 0
        }

        for row in results:
            pos = row.positive_count or 0
            neg = row.negative_count or 0
            ratio = round(pos / neg, 2) if neg > 0 else pos
            teacher_data = {
                'staff': row.Staff,
                'interactions': row.interactions or 0,
                'positive_count': pos,
                'negative_count': neg,
                'ratio': ratio,
                'total_earned': float(row.total_earned or 0),
                'total_lost': float(row.total_lost or 0),
                'unique_students': row.unique_students or 0
            }
            teachers.append(teacher_data)

            for key in school_totals:
                school_totals[key] += teacher_data.get(key, 0)

        nt_pos = school_totals['positive_count']
        nt_neg = school_totals['negative_count']
        school_totals['ratio'] = round(nt_pos / nt_neg, 2) if nt_neg > 0 else nt_pos

        logger.info(f"Kickboard teachers: {len(teachers)} teachers for {school}")
        return jsonify({'teachers': teachers, 'school_totals': school_totals, 'school': school})

    except Exception as e:
        logger.error(f"Error fetching kickboard teachers: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/kickboard/students', methods=['GET'])
@login_required
def kickboard_students():
    """Student list for one school+grade (drill-down level 2)."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)

    school = request.args.get('school', '')
    grade = request.args.get('grade', '')

    if not school:
        return jsonify({'error': 'School is required.'}), 400
    if not grade:
        return jsonify({'error': 'Grade is required.'}), 400

    category = request.args.get('category', '')
    staff = request.args.get('staff', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conditions = ["School = @school", "CAST(Grade_Level AS STRING) = @grade", "Staff != 'System Administrator'"] + acl_conds
    params = [
        bigquery.ScalarQueryParameter("school", "STRING", school),
        bigquery.ScalarQueryParameter("grade", "STRING", str(grade)),
    ] + list(acl_params)

    if category:
        conditions.append("Category = @category")
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    if staff:
        conditions.append("Staff = @staff")
        params.append(bigquery.ScalarQueryParameter("staff", "STRING", staff))
    if date_from:
        conditions.append("Interaction_Date >= @date_from")
        params.append(bigquery.ScalarQueryParameter("date_from", "STRING", date_from))
    if date_to:
        conditions.append("Interaction_Date <= @date_to")
        params.append(bigquery.ScalarQueryParameter("date_to", "STRING", date_to))

    where_clause = " AND ".join(conditions)

    try:
        query = f"""
            SELECT
                Student_Number,
                Student_LastFirst,
                COUNT(*) as interactions,
                COUNTIF(Dollar_Value > 0) as positive_count,
                COUNTIF(Dollar_Value < 0) as negative_count,
                SUM(Dollar_Value) as net_dollars,
                MAX(Interaction_Date) as last_interaction_date
            FROM `{table}`
            WHERE {where_clause}
            GROUP BY Student_Number, Student_LastFirst
            ORDER BY Student_LastFirst
        """

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        students = []
        for row in results:
            pos = row.positive_count or 0
            neg = row.negative_count or 0
            ratio = round(pos / neg, 2) if neg > 0 else pos
            students.append({
                'student_number': row.Student_Number,
                'name': row.Student_LastFirst,
                'interactions': row.interactions or 0,
                'positive_count': pos,
                'negative_count': neg,
                'ratio': ratio,
                'net_dollars': float(row.net_dollars or 0),
                'last_interaction_date': row.last_interaction_date.isoformat() if row.last_interaction_date else None
            })

        logger.info(f"Kickboard students: {len(students)} students for {school} grade {grade}")
        return jsonify({'students': students, 'school': school, 'grade': grade})

    except Exception as e:
        logger.error(f"Error fetching kickboard students: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/kickboard/interactions', methods=['GET'])
@login_required
def kickboard_interactions():
    """Individual interactions for one student (drill-down level 3). Includes Deposits."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)

    student_number = request.args.get('student_number', '')
    if not student_number:
        return jsonify({'error': 'student_number is required.'}), 400

    category = request.args.get('category', '')
    staff = request.args.get('staff', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conditions = ["Student_Number = @student_number"] + acl_conds
    params = [bigquery.ScalarQueryParameter("student_number", "STRING", student_number)] + list(acl_params)

    if category:
        conditions.append("Category = @category")
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    if staff:
        conditions.append("Staff = @staff")
        params.append(bigquery.ScalarQueryParameter("staff", "STRING", staff))
    if date_from:
        conditions.append("Interaction_Date >= @date_from")
        params.append(bigquery.ScalarQueryParameter("date_from", "STRING", date_from))
    if date_to:
        conditions.append("Interaction_Date <= @date_to")
        params.append(bigquery.ScalarQueryParameter("date_to", "STRING", date_to))

    where_clause = " AND ".join(conditions)

    try:
        query = f"""
            SELECT
                Interaction_Date,
                Interaction,
                Category,
                Dollar_Value,
                Staff,
                Comments,
                School,
                Grade_Level,
                Student_LastFirst
            FROM `{table}`
            WHERE {where_clause}
            ORDER BY Interaction_Date DESC
        """

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        interactions = []
        student_name = ''
        student_school = ''
        student_grade = ''

        for row in results:
            if not student_name and row.Student_LastFirst:
                student_name = row.Student_LastFirst
                student_school = row.School
                student_grade = row.Grade_Level

            interactions.append({
                'date': row.Interaction_Date.isoformat() if row.Interaction_Date else None,
                'interaction': row.Interaction,
                'category': row.Category,
                'dollar_value': float(row.Dollar_Value) if row.Dollar_Value else 0,
                'staff': row.Staff,
                'comments': row.Comments
            })

        logger.info(f"Kickboard interactions: {len(interactions)} for student {student_number}")
        return jsonify({
            'interactions': interactions,
            'student_name': student_name,
            'student_school': student_school,
            'student_grade': student_grade
        })

    except Exception as e:
        logger.error(f"Error fetching kickboard interactions: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/kickboard/teacher-interactions', methods=['GET'])
@login_required
def kickboard_teacher_interactions():
    """Individual interactions logged by a specific teacher."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)

    teacher = request.args.get('teacher', '')
    if not teacher:
        return jsonify({'error': 'teacher is required.'}), 400

    school = request.args.get('school', '')
    category = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conditions = ["Staff = @teacher"] + acl_conds
    params = [bigquery.ScalarQueryParameter("teacher", "STRING", teacher)] + list(acl_params)

    if school:
        conditions.append("School = @school")
        params.append(bigquery.ScalarQueryParameter("school", "STRING", school))
    if category:
        conditions.append("Category = @category")
        params.append(bigquery.ScalarQueryParameter("category", "STRING", category))
    if date_from:
        conditions.append("Interaction_Date >= @date_from")
        params.append(bigquery.ScalarQueryParameter("date_from", "STRING", date_from))
    if date_to:
        conditions.append("Interaction_Date <= @date_to")
        params.append(bigquery.ScalarQueryParameter("date_to", "STRING", date_to))

    where_clause = " AND ".join(conditions)

    try:
        query = f"""
            SELECT
                Interaction_Date,
                Interaction,
                Category,
                Dollar_Value,
                Student_LastFirst,
                Grade_Level,
                School,
                Comments
            FROM `{table}`
            WHERE {where_clause}
            ORDER BY Interaction_Date DESC
            LIMIT 500
        """

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        interactions = []
        teacher_school = ''

        for row in results:
            if not teacher_school and row.School:
                teacher_school = row.School

            interactions.append({
                'date': row.Interaction_Date.isoformat() if row.Interaction_Date else None,
                'interaction': row.Interaction,
                'category': row.Category,
                'dollar_value': float(row.Dollar_Value) if row.Dollar_Value else 0,
                'student': row.Student_LastFirst,
                'grade': row.Grade_Level,
                'comments': row.Comments
            })

        logger.info(f"Kickboard teacher interactions: {len(interactions)} for {teacher}")
        return jsonify({
            'interactions': interactions,
            'teacher': teacher,
            'school': teacher_school
        })

    except Exception as e:
        logger.error(f"Error fetching kickboard teacher interactions: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/kickboard/filter-options', methods=['GET'])
@login_required
def kickboard_filter_options():
    """Populate filter dropdowns for the Kickboard dashboard."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()
    access = get_kickboard_access(user_email)

    if not access:
        return jsonify({'error': 'Access denied.'}), 403

    table, acl_conds, acl_params = _get_table_and_access_condition(user_email, access)
    acl_where = " AND ".join(acl_conds) if acl_conds else "1=1"

    try:
        # Use WITH clause to avoid repeating parameters
        query = f"""
            WITH accessible_data AS (
                SELECT School, Grade_Level, Category, Staff, UKG_Staff_ID
                FROM `{table}`
                WHERE {acl_where}
            )
            SELECT 'school' as option_type, School as value
            FROM accessible_data
            GROUP BY School
            UNION ALL
            SELECT 'grade' as option_type, CAST(Grade_Level AS STRING) as value
            FROM accessible_data
            WHERE Grade_Level IS NOT NULL
            GROUP BY Grade_Level
            UNION ALL
            SELECT 'category' as option_type, Category as value
            FROM accessible_data
            WHERE Category IS NOT NULL
            GROUP BY Category
            UNION ALL
            SELECT 'staff' as option_type, k.Staff as value
            FROM accessible_data k
            INNER JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` s
                ON k.UKG_Staff_ID = CAST(s.Employee_Number AS STRING)
            WHERE k.Staff IS NOT NULL AND k.Staff != 'System Administrator'
            AND s.Employment_Status IN ('Active', 'Leave of absence')
            GROUP BY k.Staff
            ORDER BY option_type, value
        """

        job_config = bigquery.QueryJobConfig(query_parameters=acl_params)
        results = list(bq_client.query(query, job_config=job_config).result())

        options = {'schools': [], 'grades': [], 'categories': [], 'staff': []}
        for row in results:
            if row.value:
                if row.option_type == 'school':
                    options['schools'].append(row.value)
                elif row.option_type == 'grade':
                    options['grades'].append(row.value)
                elif row.option_type == 'category':
                    options['categories'].append(row.value)
                elif row.option_type == 'staff':
                    options['staff'].append(row.value)

        options['school_start_date'] = get_school_start_date()

        logger.info(f"Kickboard filter options: {len(options['schools'])} schools, {len(options['grades'])} grades")
        return jsonify(options)

    except Exception as e:
        logger.error(f"Error fetching kickboard filter options: {e}")
        return jsonify({'error': str(e)}), 500
