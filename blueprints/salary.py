"""
Salary Projection Dashboard Blueprint
Interactive salary scenario modeling for CEO presentations
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for
from functools import wraps
from google.cloud import bigquery
import os

bp = Blueprint('salary', __name__)

# Import config
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_ID
from extensions import bq_client
from auth import login_required, get_salary_access


def salary_access_required(f):
    """Decorator to protect salary routes - requires C-Team access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        email = session.get('user', {}).get('email', '')
        access = get_salary_access(email)

        if not access or not access.get('has_access'):
            return jsonify({'error': 'Access denied. This dashboard is restricted to C-Team.'}), 403

        return f(*args, **kwargs)
    return decorated_function

HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAFF_TABLE = f'{PROJECT_ID}.talent_grow_observations.staff_master_list_with_function'
SALARY_SCHEDULE_TABLE = f'{PROJECT_ID}.Salary.salary_schedule'

# Teacher $50K Schedule - specific step values (step 0-30)
TEACHER_50K_SCHEDULE = [
    50000, 51000, 53040, 53575, 54115, 58445, 59030, 59625, 60225, 62635,
    63265, 63900, 64540, 65190, 65845, 66505, 67175, 67850, 68530, 69220,
    69915, 70615, 71325, 72040, 72765, 73495, 74230, 74975, 75725, 76485,
    77250
]

# Years of Service Bonus Schedule (based on hire date, not experience)
# Default values - can be adjusted via UI
YOS_BONUS_DEFAULT = {
    'tier1_max': 2,     # Years 1-2
    'tier1_amount': 500,
    'tier2_max': 5,     # Years 3-5
    'tier2_amount': 750,
    'tier3_max': 9,     # Years 6-9
    'tier3_amount': 1000,
    'tier4_amount': 1250  # Years 10+
}


@bp.route('/salary-dashboard')
def serve_dashboard():
    """Serve the salary dashboard HTML."""
    from app import serve_html
    return serve_html(os.path.join(HTML_DIR, 'salary-dashboard.html'))


@bp.route('/api/salary/access')
def check_salary_access():
    """Check if user has access to salary dashboard."""
    if 'user' not in session:
        return jsonify({'has_access': False, 'reason': 'Not authenticated'})

    email = session.get('user', {}).get('email', '')
    access = get_salary_access(email)

    if access and access.get('has_access'):
        return jsonify({
            'has_access': True,
            'access_type': access.get('access_type'),
            'label': access.get('label')
        })

    return jsonify({
        'has_access': False,
        'reason': 'This dashboard is restricted to C-Team (Chief and Ex. Dir titles only).'
    })


@bp.route('/api/salary/summary')
@salary_access_required
def get_salary_summary():
    """
    Get salary projections with configurable parameters.

    Query params:
    - step_cap: Maximum step to use (default 30)
    - scenario: 'base', 'option1', 'option2', or 'all' (default 'all')
    - school: Filter by school (optional)
    - yos_bonus: If 'true', include years of service bonus calculations
    - yos_tier1_max, yos_tier1_amount, etc: YOS bonus tier settings
    """
    step_cap = int(request.args.get('step_cap', 30))
    school = request.args.get('school', '')

    # YOS bonus parameters for base comparison
    yos_bonus = request.args.get('yos_bonus', 'false').lower() == 'true'
    yos_tier1_max = int(request.args.get('yos_tier1_max', YOS_BONUS_DEFAULT['tier1_max']))
    yos_tier1_amount = float(request.args.get('yos_tier1_amount', YOS_BONUS_DEFAULT['tier1_amount']))
    yos_tier2_max = int(request.args.get('yos_tier2_max', YOS_BONUS_DEFAULT['tier2_max']))
    yos_tier2_amount = float(request.args.get('yos_tier2_amount', YOS_BONUS_DEFAULT['tier2_amount']))
    yos_tier3_max = int(request.args.get('yos_tier3_max', YOS_BONUS_DEFAULT['tier3_max']))
    yos_tier3_amount = float(request.args.get('yos_tier3_amount', YOS_BONUS_DEFAULT['tier3_amount']))
    yos_tier4_amount = float(request.args.get('yos_tier4_amount', YOS_BONUS_DEFAULT['tier4_amount']))

    query_params = []
    school_filter = ""
    if school:
        school_filter = "AND Location_Name = @school_param"
        query_params.append(bigquery.ScalarQueryParameter("school_param", "STRING", school))

    # Build YOS bonus formulas
    if yos_bonus:
        current_yos_formula = f"""
          CASE
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) < 1 THEN 0
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) <= {yos_tier1_max} THEN {yos_tier1_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) <= {yos_tier2_max} THEN {yos_tier2_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) <= {yos_tier3_max} THEN {yos_tier3_amount}
            ELSE {yos_tier4_amount}
          END
        """
        next_yos_formula = f"""
          CASE
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 < 1 THEN 0
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 <= {yos_tier1_max} THEN {yos_tier1_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 <= {yos_tier2_max} THEN {yos_tier2_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 <= {yos_tier3_max} THEN {yos_tier3_amount}
            ELSE {yos_tier4_amount}
          END
        """
        yos_select = f"""
            ({current_yos_formula}) as current_yos_bonus,
            ({next_yos_formula}) as next_yos_bonus,
        """
        yos_sum = """
            ROUND(SUM(current_yos_bonus), 0) as current_yos_bonus_total,
            ROUND(SUM(next_yos_bonus), 0) as next_yos_bonus_total,
        """
    else:
        yos_select = "0 as current_yos_bonus, 0 as next_yos_bonus,"
        yos_sum = "0 as current_yos_bonus_total, 0 as next_yos_bonus_total,"

    query = f"""
    WITH
    staff AS (
      SELECT
        Employee_Number,
        Employee_Name__Last_Suffix__First_MI_ as name,
        Job_Title,
        Location_Name as school,
        Last_Hire_Date,
        Relevant_Years_of_Experience as current_yoe,
        -- For schedule lookup: cap at 30 (schedule max)
        LEAST(COALESCE(Relevant_Years_of_Experience, 0), 30) as current_step,
        LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, 30) as next_year_step_schedule,
        -- For Option 1 / Custom: use user-selected cap
        LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, {step_cap}) as next_year_step_capped,
        CASE
          WHEN LOWER(Job_Title) LIKE "%paraprofessional%" THEN "Paraprofessional"
          WHEN LOWER(Job_Title) LIKE "%asst teacher%" OR LOWER(Job_Title) LIKE "%assistant teacher%" THEN "Asst_Teacher"
          WHEN LOWER(Job_Title) LIKE "%teacher%" THEN "Teacher"
          ELSE NULL
        END as salary_category
      FROM `{STAFF_TABLE}`
      WHERE Employment_Status IN ("Active", "Leave of absence")
      {school_filter}
    ),
    projections AS (
      SELECT
        s.*,
        -- Current salary (schedule max at 30)
        CASE s.salary_category
          WHEN "Paraprofessional" THEN curr.paraprofessional
          WHEN "Asst_Teacher" THEN curr.asst_teacher
          WHEN "Teacher" THEN curr.teacher
        END as current_salary,
        -- Next year base (schedule max at 30)
        CASE s.salary_category
          WHEN "Paraprofessional" THEN next_schedule.paraprofessional
          WHEN "Asst_Teacher" THEN next_schedule.asst_teacher
          WHEN "Teacher" THEN next_schedule.teacher
        END as next_base,
        -- Option 1 (user-selected cap)
        CASE s.salary_category
          WHEN "Paraprofessional" THEN next_capped.paraprofessional_option
          WHEN "Asst_Teacher" THEN next_capped.asst_teacher_option
          WHEN "Teacher" THEN next_capped.teacher_option_1
        END as next_opt1,
        -- Option 2 (Teacher only, user-selected cap)
        CASE s.salary_category
          WHEN "Teacher" THEN next_capped.teacher_option_2
          ELSE NULL
        END as next_opt2,
        -- YOS bonus
        {yos_select}
        -- Years of service
        FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), DAY) / 365.25) as years_of_service
      FROM staff s
      LEFT JOIN `{SALARY_SCHEDULE_TABLE}` curr
        ON curr.step = s.current_step
      LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next_schedule
        ON next_schedule.step = s.next_year_step_schedule
      LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next_capped
        ON next_capped.step = s.next_year_step_capped
      WHERE s.salary_category IS NOT NULL
    )
    SELECT
      salary_category,
      COUNT(*) as employee_count,
      ROUND(SUM(current_salary), 0) as current_total,
      ROUND(SUM(next_base), 0) as next_base_total,
      ROUND(SUM(next_opt1), 0) as next_opt1_total,
      ROUND(SUM(next_opt2), 0) as next_opt2_total,
      {yos_sum}
      ROUND(AVG(current_yoe), 1) as avg_yoe,
      SUM(CASE WHEN current_yoe > 20 THEN 1 ELSE 0 END) as above_20_years,
      SUM(CASE WHEN current_yoe > 15 THEN 1 ELSE 0 END) as above_15_years,
      SUM(CASE WHEN current_yoe > 10 THEN 1 ELSE 0 END) as above_10_years
    FROM projections
    GROUP BY salary_category
    ORDER BY salary_category
    """

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    results = bq_client.query(query, job_config=job_config).result()

    categories = []
    totals = {
        'employee_count': 0,
        'current_total': 0,
        'next_base_total': 0,
        'next_opt1_total': 0,
        'next_opt2_total': 0,
        'current_yos_bonus_total': 0,
        'next_yos_bonus_total': 0,
        'above_20_years': 0,
        'above_15_years': 0,
        'above_10_years': 0
    }

    for row in results:
        emp_count = row.employee_count or 1
        current = row.current_total or 0
        base = row.next_base_total or 0
        opt1 = row.next_opt1_total or 0

        cat = {
            'category': row.salary_category,
            'employee_count': row.employee_count,
            'current_total': current,
            'next_base_total': base,
            'next_opt1_total': opt1,
            'next_opt2_total': row.next_opt2_total or 0,
            'current_yos_bonus_total': getattr(row, 'current_yos_bonus_total', 0) or 0,
            'next_yos_bonus_total': getattr(row, 'next_yos_bonus_total', 0) or 0,
            'avg_yoe': row.avg_yoe or 0,
            'above_20_years': row.above_20_years or 0,
            'above_15_years': row.above_15_years or 0,
            'above_10_years': row.above_10_years or 0,
            'avg_raise_base': round((base - current) / emp_count, 0) if emp_count else 0,
            'avg_raise_opt1': round((opt1 - current) / emp_count, 0) if emp_count else 0,
        }
        categories.append(cat)

        for key in totals:
            totals[key] += cat.get(key, 0)

    return jsonify({
        'step_cap': step_cap,
        'yos_bonus_enabled': yos_bonus,
        'yos_tiers': {
            'tier1_max': yos_tier1_max,
            'tier1_amount': yos_tier1_amount,
            'tier2_max': yos_tier2_max,
            'tier2_amount': yos_tier2_amount,
            'tier3_max': yos_tier3_max,
            'tier3_amount': yos_tier3_amount,
            'tier4_amount': yos_tier4_amount
        } if yos_bonus else None,
        'categories': categories,
        'totals': totals
    })


@bp.route('/api/salary/distribution')
@salary_access_required
def get_yoe_distribution():
    """Get distribution of years of experience."""
    school = request.args.get('school', '')
    category = request.args.get('category', '')

    query_params = []
    conditions = ['Employment_Status IN ("Active", "Leave of absence")']
    if school:
        conditions.append('Location_Name = @school_param')
        query_params.append(bigquery.ScalarQueryParameter("school_param", "STRING", school))

    category_case = """
    CASE
      WHEN LOWER(Job_Title) LIKE "%paraprofessional%" THEN "Paraprofessional"
      WHEN LOWER(Job_Title) LIKE "%asst teacher%" OR LOWER(Job_Title) LIKE "%assistant teacher%" THEN "Asst_Teacher"
      WHEN LOWER(Job_Title) LIKE "%teacher%" THEN "Teacher"
      ELSE NULL
    END
    """

    if category:
        conditions.append(f'({category_case}) = @category_param')
        query_params.append(bigquery.ScalarQueryParameter("category_param", "STRING", category))
    else:
        conditions.append(f'({category_case}) IS NOT NULL')

    where_clause = ' AND '.join(conditions)

    query = f"""
    SELECT
      COALESCE(Relevant_Years_of_Experience, 0) as yoe,
      COUNT(*) as count
    FROM `{STAFF_TABLE}`
    WHERE {where_clause}
    GROUP BY yoe
    ORDER BY yoe
    """

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    results = bq_client.query(query, job_config=job_config).result()

    distribution = [{'yoe': row.yoe, 'count': row.count} for row in results]

    return jsonify({'distribution': distribution})


@bp.route('/api/salary/employees')
@salary_access_required
def get_employees():
    """Get employee list with salary details, including custom scenario if provided."""
    step_cap = int(request.args.get('step_cap', 30))
    school = request.args.get('school', '')
    category = request.args.get('category', '')
    min_yoe = request.args.get('min_yoe', '')
    max_yoe = request.args.get('max_yoe', '')

    # Custom scenario parameters
    custom_mode = request.args.get('custom_mode', 'false').lower() == 'true'
    para_schedule = request.args.get('para_schedule', 'false').lower() == 'true'
    asst_schedule = request.args.get('asst_schedule', 'false').lower() == 'true'
    teacher_schedule = request.args.get('teacher_schedule', 'false').lower() == 'true'
    base_para = request.args.get('base_para', '')
    base_asst = request.args.get('base_asst', '')
    base_teacher = request.args.get('base_teacher', '')
    annual_increase = float(request.args.get('annual_increase', 0))
    teacher_hybrid = request.args.get('teacher_hybrid', 'false').lower() == 'true' and not teacher_schedule
    hybrid_threshold = int(request.args.get('hybrid_threshold', 10))
    hybrid_rate_1 = float(request.args.get('hybrid_rate_1', 2.0))
    hybrid_rate_2 = float(request.args.get('hybrid_rate_2', 1.5))
    teacher_50k = request.args.get('teacher_50k', 'false').lower() == 'true'

    # YOS bonus parameters
    yos_bonus = request.args.get('yos_bonus', 'false').lower() == 'true'
    yos_tier1_max = int(request.args.get('yos_tier1_max', YOS_BONUS_DEFAULT['tier1_max']))
    yos_tier1_amount = float(request.args.get('yos_tier1_amount', YOS_BONUS_DEFAULT['tier1_amount']))
    yos_tier2_max = int(request.args.get('yos_tier2_max', YOS_BONUS_DEFAULT['tier2_max']))
    yos_tier2_amount = float(request.args.get('yos_tier2_amount', YOS_BONUS_DEFAULT['tier2_amount']))
    yos_tier3_max = int(request.args.get('yos_tier3_max', YOS_BONUS_DEFAULT['tier3_max']))
    yos_tier3_amount = float(request.args.get('yos_tier3_amount', YOS_BONUS_DEFAULT['tier3_amount']))
    yos_tier4_amount = float(request.args.get('yos_tier4_amount', YOS_BONUS_DEFAULT['tier4_amount']))

    query_params = []
    conditions = ['Employment_Status IN ("Active", "Leave of absence")']
    if school:
        conditions.append('Location_Name = @school_param')
        query_params.append(bigquery.ScalarQueryParameter("school_param", "STRING", school))

    where_clause = ' AND '.join(conditions)

    # Build YOS bonus formulas for employees (current year and next year)
    if yos_bonus:
        yos_bonus_formula_current = f"""
          CASE
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) < 1 THEN 0
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) <= {yos_tier1_max} THEN {yos_tier1_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) <= {yos_tier2_max} THEN {yos_tier2_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) <= {yos_tier3_max} THEN {yos_tier3_amount}
            ELSE {yos_tier4_amount}
          END
        """
        yos_bonus_formula_next = f"""
          CASE
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 < 1 THEN 0
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 <= {yos_tier1_max} THEN {yos_tier1_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 <= {yos_tier2_max} THEN {yos_tier2_amount}
            WHEN FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 <= {yos_tier3_max} THEN {yos_tier3_amount}
            ELSE {yos_tier4_amount}
          END
        """
    else:
        yos_bonus_formula_current = "0"
        yos_bonus_formula_next = "0"

    # Build custom salary formulas if in custom mode
    has_custom_base = (base_para and base_para != '28850') or (base_asst and base_asst != '31900') or (base_teacher and base_teacher != '48000')
    if custom_mode and (annual_increase > 0 or teacher_hybrid or teacher_50k or yos_bonus or has_custom_base):
        base_para = float(base_para) if base_para else 28850
        base_asst = float(base_asst) if base_asst else 31900
        base_teacher = float(base_teacher) if base_teacher else 48000
        rate = 1 + (annual_increase / 100) if annual_increase > 0 else 1.02
        rate1 = 1 + (hybrid_rate_1 / 100)
        rate2 = 1 + (hybrid_rate_2 / 100)

        # Para formula
        if para_schedule:
            para_next_formula = "next_capped.paraprofessional"
        else:
            para_next_formula = f"{base_para} * POWER({rate}, s.next_year_step)"

        # Asst formula
        if asst_schedule:
            asst_next_formula = "next_capped.asst_teacher"
        else:
            asst_next_formula = f"{base_asst} * POWER({rate}, s.next_year_step)"

        # Teacher formula
        if teacher_schedule:
            teacher_next_formula = "next_capped.teacher"
        elif teacher_50k:
            # Use the $50K schedule lookup table
            schedule_cases = " ".join([f"WHEN s.next_year_step = {i} THEN {v}" for i, v in enumerate(TEACHER_50K_SCHEDULE)])
            teacher_next_formula = f"CASE {schedule_cases} ELSE {TEACHER_50K_SCHEDULE[-1]} END"
        elif teacher_hybrid:
            teacher_next_formula = f"""
              CASE
                WHEN s.next_year_step <= {hybrid_threshold} THEN {base_teacher} * POWER({rate1}, s.next_year_step)
                ELSE {base_teacher} * POWER({rate1}, {hybrid_threshold}) * POWER({rate2}, s.next_year_step - {hybrid_threshold})
              END
            """
        else:
            teacher_next_formula = f"{base_teacher} * POWER({rate}, s.next_year_step)"

        custom_salary_select = f"""
            (CASE s.salary_category
              WHEN "Paraprofessional" THEN {para_next_formula}
              WHEN "Asst_Teacher" THEN {asst_next_formula}
              WHEN "Teacher" THEN {teacher_next_formula}
            END) + ({yos_bonus_formula_next}) as next_custom,
            ({yos_bonus_formula_current}) as current_yos_bonus,
            ({yos_bonus_formula_next}) as yos_bonus,
            FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) as years_of_service,
        """
    elif yos_bonus:
        # Not in custom mode but YOS bonus is enabled - still calculate YOS bonus
        custom_salary_select = f"""
            NULL as next_custom,
            ({yos_bonus_formula_current}) as current_yos_bonus,
            ({yos_bonus_formula_next}) as yos_bonus,
            FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) as years_of_service,
        """
    else:
        custom_salary_select = "NULL as next_custom, 0 as current_yos_bonus, 0 as yos_bonus, FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) as years_of_service,"

    # Build extra filters with parameterized queries
    extra_filters = ""
    if category:
        extra_filters += "\n    AND salary_category = @category_param"
        query_params.append(bigquery.ScalarQueryParameter("category_param", "STRING", category))
    if min_yoe:
        extra_filters += f"\n    AND current_yoe >= {int(min_yoe)}"
    if max_yoe:
        extra_filters += f"\n    AND current_yoe <= {int(max_yoe)}"

    query = f"""
    WITH
    staff AS (
      SELECT
        Employee_Number,
        Employee_Name__Last_Suffix__First_MI_ as name,
        Job_Title,
        Location_Name as school,
        Last_Hire_Date,
        Relevant_Years_of_Experience as current_yoe,
        -- For schedule lookup: cap at 30 (schedule max)
        LEAST(COALESCE(Relevant_Years_of_Experience, 0), 30) as current_step,
        LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, 30) as next_year_step_schedule,
        -- For Option 1 / Custom: use user-selected cap
        LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, {step_cap}) as next_year_step,
        CASE
          WHEN LOWER(Job_Title) LIKE "%paraprofessional%" THEN "Paraprofessional"
          WHEN LOWER(Job_Title) LIKE "%asst teacher%" OR LOWER(Job_Title) LIKE "%assistant teacher%" THEN "Asst_Teacher"
          WHEN LOWER(Job_Title) LIKE "%teacher%" THEN "Teacher"
          ELSE NULL
        END as salary_category
      FROM `{STAFF_TABLE}`
      WHERE {where_clause}
    ),
    projections AS (
      SELECT
        s.*,
        CASE s.salary_category
          WHEN "Paraprofessional" THEN curr.paraprofessional
          WHEN "Asst_Teacher" THEN curr.asst_teacher
          WHEN "Teacher" THEN curr.teacher
        END as current_salary,
        CASE s.salary_category
          WHEN "Paraprofessional" THEN next_schedule.paraprofessional
          WHEN "Asst_Teacher" THEN next_schedule.asst_teacher
          WHEN "Teacher" THEN next_schedule.teacher
        END as next_base,
        CASE s.salary_category
          WHEN "Paraprofessional" THEN next_capped.paraprofessional_option
          WHEN "Asst_Teacher" THEN next_capped.asst_teacher_option
          WHEN "Teacher" THEN next_capped.teacher_option_1
        END as next_opt1,
        {custom_salary_select}
        CASE s.salary_category
          WHEN "Teacher" THEN next_capped.teacher_option_2
          ELSE NULL
        END as next_opt2
      FROM staff s
      LEFT JOIN `{SALARY_SCHEDULE_TABLE}` curr
        ON curr.step = s.current_step
      LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next_schedule
        ON next_schedule.step = s.next_year_step_schedule
      LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next_capped
        ON next_capped.step = s.next_year_step
      WHERE s.salary_category IS NOT NULL
    )
    SELECT *
    FROM projections
    WHERE 1=1
    {extra_filters}
    ORDER BY salary_category, current_yoe DESC, name
    """

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    results = bq_client.query(query, job_config=job_config).result()

    employees = []
    for row in results:
        emp = {
            'employee_number': row.Employee_Number,
            'name': row.name,
            'job_title': row.Job_Title,
            'school': row.school,
            'category': row.salary_category,
            'current_yoe': row.current_yoe or 0,
            'next_step': row.next_year_step,
            'current_salary': row.current_salary or 0,
            'next_base': row.next_base or 0,
            'next_opt1': row.next_opt1 or 0,
            'next_opt2': row.next_opt2,
            'years_of_service': getattr(row, 'years_of_service', None) or 0,
            'current_yos_bonus': getattr(row, 'current_yos_bonus', 0) or 0,
            'yos_bonus': getattr(row, 'yos_bonus', 0) or 0
        }
        if custom_mode:
            emp['next_custom'] = row.next_custom or 0
        employees.append(emp)

    return jsonify({'employees': employees, 'custom_mode': custom_mode, 'yos_bonus_enabled': yos_bonus})


@bp.route('/api/salary/schools')
@salary_access_required
def get_schools():
    """Get list of schools for filter dropdown."""
    query = f"""
    SELECT DISTINCT Location_Name as school
    FROM `{STAFF_TABLE}`
    WHERE Employment_Status IN ("Active", "Leave of absence")
      AND Location_Name IS NOT NULL
    ORDER BY school
    """

    results = bq_client.query(query).result()
    schools = [row.school for row in results]

    return jsonify({'schools': schools})


@bp.route('/api/salary/schedule')
@salary_access_required
def get_salary_schedule():
    """Get the full salary schedule for reference."""
    query = f"""
    SELECT *
    FROM `{SALARY_SCHEDULE_TABLE}`
    ORDER BY step
    """

    results = bq_client.query(query).result()

    schedule = []
    for row in results:
        schedule.append({
            'step': row.step,
            'paraprofessional': row.paraprofessional,
            'paraprofessional_option': row.paraprofessional_option,
            'asst_teacher': row.asst_teacher,
            'asst_teacher_option': row.asst_teacher_option,
            'teacher': row.teacher,
            'teacher_option_1': row.teacher_option_1,
            'teacher_option_2': row.teacher_option_2
        })

    return jsonify({'schedule': schedule})


@bp.route('/api/salary/compare-caps')
@salary_access_required
def compare_step_caps():
    """Compare different step cap scenarios side by side."""
    caps = request.args.get('caps', '15,20,25,30').split(',')
    school = request.args.get('school', '')

    query_params = []
    school_filter = ""
    if school:
        school_filter = "AND Location_Name = @school_param"
        query_params.append(bigquery.ScalarQueryParameter("school_param", "STRING", school))

    results = []

    for cap in caps:
        cap = int(cap.strip())

        query = f"""
        WITH
        staff AS (
          SELECT
            Employee_Number,
            Job_Title,
            Relevant_Years_of_Experience as current_yoe,
            -- For schedule lookup: cap at 30 (schedule max)
            LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, 30) as next_year_step_schedule,
            -- For Option 1: use comparison cap
            LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, {cap}) as next_year_step_capped,
            CASE
              WHEN LOWER(Job_Title) LIKE "%paraprofessional%" THEN "Paraprofessional"
              WHEN LOWER(Job_Title) LIKE "%asst teacher%" OR LOWER(Job_Title) LIKE "%assistant teacher%" THEN "Asst_Teacher"
              WHEN LOWER(Job_Title) LIKE "%teacher%" THEN "Teacher"
              ELSE NULL
            END as salary_category
          FROM `{STAFF_TABLE}`
          WHERE Employment_Status IN ("Active", "Leave of absence")
          {school_filter}
        ),
        projections AS (
          SELECT
            s.*,
            -- Base uses schedule (max at 30)
            CASE s.salary_category
              WHEN "Paraprofessional" THEN next_schedule.paraprofessional
              WHEN "Asst_Teacher" THEN next_schedule.asst_teacher
              WHEN "Teacher" THEN next_schedule.teacher
            END as next_base,
            -- Option 1 uses comparison cap
            CASE s.salary_category
              WHEN "Paraprofessional" THEN next_capped.paraprofessional_option
              WHEN "Asst_Teacher" THEN next_capped.asst_teacher_option
              WHEN "Teacher" THEN next_capped.teacher_option_1
            END as next_opt1,
            CASE s.salary_category
              WHEN "Teacher" THEN next_capped.teacher_option_2
              ELSE NULL
            END as next_opt2
          FROM staff s
          LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next_schedule
            ON next_schedule.step = s.next_year_step_schedule
          LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next_capped
            ON next_capped.step = s.next_year_step_capped
          WHERE s.salary_category IS NOT NULL
        )
        SELECT
          COUNT(*) as employee_count,
          ROUND(SUM(next_base), 0) as base_total,
          ROUND(SUM(next_opt1), 0) as opt1_total,
          SUM(CASE WHEN current_yoe > {cap} THEN 1 ELSE 0 END) as capped_count
        FROM projections
        """

        job_config = bigquery.QueryJobConfig(query_parameters=query_params)
        row = list(bq_client.query(query, job_config=job_config).result())[0]

        results.append({
            'step_cap': cap,
            'employee_count': row.employee_count,
            'base_total': row.base_total or 0,
            'opt1_total': row.opt1_total or 0,
            'capped_count': row.capped_count or 0
        })

    return jsonify({'comparisons': results})


@bp.route('/api/salary/custom-scenario')
@salary_access_required
def custom_scenario():
    """
    Model custom salary scenarios with adjustable parameters.

    Query params:
    - step_cap: Maximum step (default 30)
    - base_para: Base salary for paraprofessional at step 0 (default from schedule)
    - base_asst: Base salary for asst teacher at step 0 (default from schedule)
    - base_teacher: Base salary for teacher at step 0 (default from schedule)
    - para_schedule: If 'true', use schedule for paras instead of custom
    - asst_schedule: If 'true', use schedule for asst teachers instead of custom
    - teacher_schedule: If 'true', use schedule for teachers instead of custom
    - annual_increase: Annual step increase percentage (default 1.0 = current schedule)
    - teacher_hybrid: If 'true', use hybrid rate for teachers (2% first 10 yrs, 1.5% after)
    - hybrid_threshold: Year when hybrid switches (default 10)
    - hybrid_rate_1: First rate percentage (default 2.0)
    - hybrid_rate_2: Second rate percentage (default 1.5)
    - school: Filter by school (optional)
    - yos_bonus: If 'true', include years of service bonus
    - yos_tier1_max: Max years for tier 1 (default 2)
    - yos_tier1_amount: Bonus for tier 1 (default 500)
    - yos_tier2_max: Max years for tier 2 (default 5)
    - yos_tier2_amount: Bonus for tier 2 (default 750)
    - yos_tier3_max: Max years for tier 3 (default 9)
    - yos_tier3_amount: Bonus for tier 3 (default 1000)
    - yos_tier4_amount: Bonus for tier 4 - 10+ years (default 1250)
    """
    step_cap = int(request.args.get('step_cap', 30))
    school = request.args.get('school', '')

    # Per-category schedule toggles
    para_schedule = request.args.get('para_schedule', 'false').lower() == 'true'
    asst_schedule = request.args.get('asst_schedule', 'false').lower() == 'true'
    teacher_schedule = request.args.get('teacher_schedule', 'false').lower() == 'true'

    # Custom scenario parameters
    base_para = request.args.get('base_para', '')
    base_asst = request.args.get('base_asst', '')
    base_teacher = request.args.get('base_teacher', '')
    annual_increase = float(request.args.get('annual_increase', 0))  # 0 means use schedule

    # Hybrid parameters for teachers
    teacher_hybrid = request.args.get('teacher_hybrid', 'false').lower() == 'true' and not teacher_schedule
    hybrid_threshold = int(request.args.get('hybrid_threshold', 10))
    hybrid_rate_1 = float(request.args.get('hybrid_rate_1', 2.0))
    hybrid_rate_2 = float(request.args.get('hybrid_rate_2', 1.5))

    # Teacher $50K schedule option
    teacher_50k = request.args.get('teacher_50k', 'false').lower() == 'true'

    # Years of Service Bonus parameters
    yos_bonus = request.args.get('yos_bonus', 'false').lower() == 'true'
    yos_tier1_max = int(request.args.get('yos_tier1_max', YOS_BONUS_DEFAULT['tier1_max']))
    yos_tier1_amount = float(request.args.get('yos_tier1_amount', YOS_BONUS_DEFAULT['tier1_amount']))
    yos_tier2_max = int(request.args.get('yos_tier2_max', YOS_BONUS_DEFAULT['tier2_max']))
    yos_tier2_amount = float(request.args.get('yos_tier2_amount', YOS_BONUS_DEFAULT['tier2_amount']))
    yos_tier3_max = int(request.args.get('yos_tier3_max', YOS_BONUS_DEFAULT['tier3_max']))
    yos_tier3_amount = float(request.args.get('yos_tier3_amount', YOS_BONUS_DEFAULT['tier3_amount']))
    yos_tier4_amount = float(request.args.get('yos_tier4_amount', YOS_BONUS_DEFAULT['tier4_amount']))

    query_params = []
    school_filter = ""
    if school:
        school_filter = "AND Location_Name = @school_param"
        query_params.append(bigquery.ScalarQueryParameter("school_param", "STRING", school))

    # Build YOS bonus formula if enabled
    if yos_bonus:
        yos_bonus_formula = f"""
          CASE
            WHEN years_of_service < 1 THEN 0
            WHEN years_of_service <= {yos_tier1_max} THEN {yos_tier1_amount}
            WHEN years_of_service <= {yos_tier2_max} THEN {yos_tier2_amount}
            WHEN years_of_service <= {yos_tier3_max} THEN {yos_tier3_amount}
            ELSE {yos_tier4_amount}
          END
        """
    else:
        yos_bonus_formula = "0"

    # Check if any category needs custom calculation
    has_custom_base = (base_para and base_para != '28850') or (base_asst and base_asst != '31900') or (base_teacher and base_teacher != '48000')
    any_custom = (not para_schedule or not asst_schedule or not teacher_schedule) and (annual_increase > 0 or has_custom_base)

    # If custom bases provided, calculate dynamically
    if any_custom or teacher_hybrid or teacher_50k or yos_bonus:
        # Use defaults from step 0 if not provided
        base_para = float(base_para) if base_para else 28850
        base_asst = float(base_asst) if base_asst else 31900
        base_teacher = float(base_teacher) if base_teacher else 48000

        rate = 1 + (annual_increase / 100) if annual_increase > 0 else 1.02  # default 2%
        rate1 = 1 + (hybrid_rate_1 / 100)
        rate2 = 1 + (hybrid_rate_2 / 100)

        # Build para salary formula - use schedule or custom
        if para_schedule:
            para_current_formula = "curr.paraprofessional"
            para_next_formula = "next.paraprofessional"
        else:
            para_current_formula = f"{base_para} * POWER({rate}, s.capped_yoe)"
            para_next_formula = f"{base_para} * POWER({rate}, s.next_year_step)"

        # Build asst teacher salary formula - use schedule or custom
        if asst_schedule:
            asst_current_formula = "curr.asst_teacher"
            asst_next_formula = "next.asst_teacher"
        else:
            asst_current_formula = f"{base_asst} * POWER({rate}, s.capped_yoe)"
            asst_next_formula = f"{base_asst} * POWER({rate}, s.next_year_step)"

        # Build teacher salary formula based on hybrid mode, $50K schedule, or regular schedule
        if teacher_schedule:
            teacher_current_formula = "curr.teacher"
            teacher_next_formula = "next.teacher"
        elif teacher_50k:
            # Use the $50K schedule lookup table
            schedule_cases_current = " ".join([f"WHEN s.capped_yoe = {i} THEN {v}" for i, v in enumerate(TEACHER_50K_SCHEDULE)])
            schedule_cases_next = " ".join([f"WHEN s.next_year_step = {i} THEN {v}" for i, v in enumerate(TEACHER_50K_SCHEDULE)])
            teacher_current_formula = f"CASE {schedule_cases_current} ELSE {TEACHER_50K_SCHEDULE[-1]} END"
            teacher_next_formula = f"CASE {schedule_cases_next} ELSE {TEACHER_50K_SCHEDULE[-1]} END"
        elif teacher_hybrid:
            # Hybrid: 2% for first N years, then 1.5%
            # Formula: IF step <= threshold: base * rate1^step
            #          ELSE: base * rate1^threshold * rate2^(step - threshold)
            teacher_current_formula = f"""
              CASE
                WHEN s.capped_yoe <= {hybrid_threshold} THEN {base_teacher} * POWER({rate1}, s.capped_yoe)
                ELSE {base_teacher} * POWER({rate1}, {hybrid_threshold}) * POWER({rate2}, s.capped_yoe - {hybrid_threshold})
              END
            """
            teacher_next_formula = f"""
              CASE
                WHEN s.next_year_step <= {hybrid_threshold} THEN {base_teacher} * POWER({rate1}, s.next_year_step)
                ELSE {base_teacher} * POWER({rate1}, {hybrid_threshold}) * POWER({rate2}, s.next_year_step - {hybrid_threshold})
              END
            """
        else:
            # Flat rate
            teacher_current_formula = f"{base_teacher} * POWER({rate}, s.capped_yoe)"
            teacher_next_formula = f"{base_teacher} * POWER({rate}, s.next_year_step)"

        query = f"""
        WITH
        staff AS (
          SELECT
            Employee_Number,
            Job_Title,
            Location_Name as school,
            Relevant_Years_of_Experience as current_yoe,
            LEAST(COALESCE(Relevant_Years_of_Experience, 0), {step_cap}) as capped_yoe,
            LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, {step_cap}) as next_year_step,
            -- Years of service from hire date
            FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) as years_of_service,
            FLOOR(DATE_DIFF(CURRENT_DATE(), DATE(Last_Hire_Date), DAY) / 365.25) + 1 as next_year_yos,
            CASE
              WHEN LOWER(Job_Title) LIKE "%paraprofessional%" THEN "Paraprofessional"
              WHEN LOWER(Job_Title) LIKE "%asst teacher%" OR LOWER(Job_Title) LIKE "%assistant teacher%" THEN "Asst_Teacher"
              WHEN LOWER(Job_Title) LIKE "%teacher%" THEN "Teacher"
              ELSE NULL
            END as salary_category
          FROM `{STAFF_TABLE}`
          WHERE Employment_Status IN ("Active", "Leave of absence")
          {school_filter}
        ),
        with_bonus AS (
          SELECT
            s.*,
            -- Current YOS bonus
            {yos_bonus_formula} as current_yos_bonus,
            -- Next year YOS bonus (using next_year_yos)
            CASE
              WHEN s.next_year_yos < 1 THEN 0
              WHEN s.next_year_yos <= {yos_tier1_max} THEN {yos_tier1_amount if yos_bonus else 0}
              WHEN s.next_year_yos <= {yos_tier2_max} THEN {yos_tier2_amount if yos_bonus else 0}
              WHEN s.next_year_yos <= {yos_tier3_max} THEN {yos_tier3_amount if yos_bonus else 0}
              ELSE {yos_tier4_amount if yos_bonus else 0}
            END as next_yos_bonus
          FROM staff s
        ),
        projections AS (
          SELECT
            s.*,
            -- Current custom salary (per-category: schedule or custom) + YOS bonus
            CASE s.salary_category
              WHEN "Paraprofessional" THEN {para_current_formula}
              WHEN "Asst_Teacher" THEN {asst_current_formula}
              WHEN "Teacher" THEN {teacher_current_formula}
            END + s.current_yos_bonus as current_custom,
            -- Next year custom salary (per-category: schedule or custom) + YOS bonus
            CASE s.salary_category
              WHEN "Paraprofessional" THEN {para_next_formula}
              WHEN "Asst_Teacher" THEN {asst_next_formula}
              WHEN "Teacher" THEN {teacher_next_formula}
            END + s.next_yos_bonus as next_custom,
            -- Current schedule salary for comparison
            CASE s.salary_category
              WHEN "Paraprofessional" THEN curr.paraprofessional
              WHEN "Asst_Teacher" THEN curr.asst_teacher
              WHEN "Teacher" THEN curr.teacher
            END as current_schedule,
            -- Next schedule salary for comparison
            CASE s.salary_category
              WHEN "Paraprofessional" THEN next.paraprofessional
              WHEN "Asst_Teacher" THEN next.asst_teacher
              WHEN "Teacher" THEN next.teacher
            END as next_schedule
          FROM with_bonus s
          LEFT JOIN `{SALARY_SCHEDULE_TABLE}` curr
            ON curr.step = s.capped_yoe
          LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next
            ON next.step = s.next_year_step
          WHERE s.salary_category IS NOT NULL
        )
        SELECT
          salary_category,
          COUNT(*) as employee_count,
          ROUND(SUM(current_schedule), 0) as current_schedule_total,
          ROUND(SUM(next_schedule), 0) as next_schedule_total,
          ROUND(SUM(current_custom), 0) as current_custom_total,
          ROUND(SUM(next_custom), 0) as next_custom_total,
          ROUND(SUM(current_yos_bonus), 0) as current_yos_bonus_total,
          ROUND(SUM(next_yos_bonus), 0) as next_yos_bonus_total,
          ROUND(AVG(current_yoe), 1) as avg_yoe
        FROM projections
        GROUP BY salary_category
        ORDER BY salary_category
        """
    else:
        # Just return schedule-based results
        query = f"""
        WITH
        staff AS (
          SELECT
            Employee_Number,
            Job_Title,
            Location_Name as school,
            Relevant_Years_of_Experience as current_yoe,
            LEAST(COALESCE(Relevant_Years_of_Experience, 0), {step_cap}) as capped_yoe,
            LEAST(COALESCE(Relevant_Years_of_Experience, 0) + 1, {step_cap}) as next_year_step,
            CASE
              WHEN LOWER(Job_Title) LIKE "%paraprofessional%" THEN "Paraprofessional"
              WHEN LOWER(Job_Title) LIKE "%asst teacher%" OR LOWER(Job_Title) LIKE "%assistant teacher%" THEN "Asst_Teacher"
              WHEN LOWER(Job_Title) LIKE "%teacher%" THEN "Teacher"
              ELSE NULL
            END as salary_category
          FROM `{STAFF_TABLE}`
          WHERE Employment_Status IN ("Active", "Leave of absence")
          {school_filter}
        ),
        projections AS (
          SELECT
            s.*,
            CASE s.salary_category
              WHEN "Paraprofessional" THEN curr.paraprofessional
              WHEN "Asst_Teacher" THEN curr.asst_teacher
              WHEN "Teacher" THEN curr.teacher
            END as current_schedule,
            CASE s.salary_category
              WHEN "Paraprofessional" THEN next.paraprofessional
              WHEN "Asst_Teacher" THEN next.asst_teacher
              WHEN "Teacher" THEN next.teacher
            END as next_schedule
          FROM staff s
          LEFT JOIN `{SALARY_SCHEDULE_TABLE}` curr
            ON curr.step = s.capped_yoe
          LEFT JOIN `{SALARY_SCHEDULE_TABLE}` next
            ON next.step = s.next_year_step
          WHERE s.salary_category IS NOT NULL
        )
        SELECT
          salary_category,
          COUNT(*) as employee_count,
          ROUND(SUM(current_schedule), 0) as current_schedule_total,
          ROUND(SUM(next_schedule), 0) as next_schedule_total,
          ROUND(SUM(current_schedule), 0) as current_custom_total,
          ROUND(SUM(next_schedule), 0) as next_custom_total,
          ROUND(AVG(current_yoe), 1) as avg_yoe
        FROM projections
        GROUP BY salary_category
        ORDER BY salary_category
        """

    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    results = bq_client.query(query, job_config=job_config).result()

    categories = []
    totals = {
        'employee_count': 0,
        'current_schedule_total': 0,
        'next_schedule_total': 0,
        'current_custom_total': 0,
        'next_custom_total': 0,
        'current_yos_bonus_total': 0,
        'next_yos_bonus_total': 0
    }

    for row in results:
        emp_count = row.employee_count or 1
        current = row.current_schedule_total or 0
        next_custom = row.next_custom_total or 0

        cat = {
            'category': row.salary_category,
            'employee_count': row.employee_count,
            'current_schedule_total': current,
            'next_schedule_total': row.next_schedule_total or 0,
            'current_custom_total': row.current_custom_total or 0,
            'next_custom_total': next_custom,
            'current_yos_bonus_total': getattr(row, 'current_yos_bonus_total', 0) or 0,
            'next_yos_bonus_total': getattr(row, 'next_yos_bonus_total', 0) or 0,
            'avg_yoe': row.avg_yoe or 0,
            'avg_raise_custom': round((next_custom - current) / emp_count, 0) if emp_count else 0,
        }
        categories.append(cat)

        for key in totals:
            totals[key] += cat.get(key, 0)

    return jsonify({
        'step_cap': step_cap,
        'base_para': base_para if base_para else 28850,
        'base_asst': base_asst if base_asst else 31900,
        'base_teacher': base_teacher if base_teacher else 48000,
        'annual_increase': annual_increase if annual_increase else 'schedule',
        'yos_bonus_enabled': yos_bonus,
        'yos_tiers': {
            'tier1_max': yos_tier1_max,
            'tier1_amount': yos_tier1_amount,
            'tier2_max': yos_tier2_max,
            'tier2_amount': yos_tier2_amount,
            'tier3_max': yos_tier3_max,
            'tier3_amount': yos_tier3_amount,
            'tier4_amount': yos_tier4_amount
        } if yos_bonus else None,
        'categories': categories,
        'totals': totals
    })
