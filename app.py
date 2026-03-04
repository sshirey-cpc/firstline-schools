"""
Position Control - Flask Backend
Standalone application for managing position control data.
"""

import os
import logging
from functools import wraps
from flask import Flask, jsonify, request, session, send_from_directory, redirect, url_for
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from google.cloud import bigquery
from authlib.integrations.flask_client import OAuth

from config import (
    SECRET_KEY, ALLOWED_ORIGINS, ALLOWED_DOMAIN,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, DEV_MODE, DEV_USER_EMAIL,
    PROJECT_ID, DATASET_ID, STAFF_TABLE, POSITION_TABLE, SITE_SCHOOLS,
    TALENT_TITLES, STAFFING_BOARD_C_TEAM_KEYWORDS, STAFFING_BOARD_TITLES
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize BigQuery client
try:
    bq_client = bigquery.Client(project=PROJECT_ID)
    logger.info(f"BigQuery client initialized for project: {PROJECT_ID}")
except Exception as e:
    logger.error(f"Failed to initialize BigQuery client: {e}")
    bq_client = None

# Create Flask app
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'development'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# OAuth setup
oauth = OAuth(app)
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

HTML_DIR = os.path.dirname(os.path.abspath(__file__))


@app.before_request
def refresh_job_title():
    """Refresh job title from BigQuery on every request so role changes take effect immediately."""
    if 'user' not in session or not bq_client:
        return
    email = session['user'].get('email', '')
    if not email:
        return
    try:
        query = f"""
            SELECT Job_Title
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE LOWER(TRIM(Email_Address)) = @email
            AND Employment_Status IN ('Active', 'Leave of absence')
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("email", "STRING", email.lower())]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        rows = list(bq_client.query(query, job_config=job_config).result())
        fresh_title = (rows[0].Job_Title or '').strip() if rows else ''
        if fresh_title != session.get('job_title', ''):
            session['job_title'] = fresh_title
            session.modified = True
    except Exception as e:
        logger.error(f"Error refreshing job title for {email}: {e}")


# Valid school years for dropdowns
SCHOOL_YEARS = ['25-26', '26-27', '27-28', '28-29', '29-30']


def year_filter_sql(year: str, start_col: str = "start_year", end_col: str = "end_year") -> str:
    """
    Generate SQL WHERE clause to filter positions by school year.
    A position applies to a year if it started on or before that year
    and either hasn't ended or ends on or after that year.
    """
    return f"({start_col} <= '{year}' AND ({end_col} >= '{year}' OR {end_col} IS NULL))"


def login_required(f):
    """Decorator to require authentication and Staffing Board access (by job title)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if DEV_MODE:
            if 'user' not in session:
                session['user'] = {
                    'email': DEV_USER_EMAIL,
                    'name': 'Dev User',
                    'picture': ''
                }
            return f(*args, **kwargs)

        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        job_title = session.get('job_title', '')
        if not has_staffing_board_access(job_title):
            return jsonify({'error': 'Staffing Board access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def has_staffing_board_access(job_title):
    """Check if a job title grants Staffing Board read access."""
    if not job_title:
        return False
    title_lower = job_title.lower()
    # C-Team keyword match (same pattern as salary dashboard)
    for keyword in STAFFING_BOARD_C_TEAM_KEYWORDS:
        if keyword.lower() in title_lower:
            return True
    # Explicit title match
    return job_title in STAFFING_BOARD_TITLES


# ─────────────────────────────────────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/login')
def login():
    """Initiate Google OAuth login."""
    if DEV_MODE:
        session['user'] = {
            'email': DEV_USER_EMAIL,
            'name': 'Dev User',
            'picture': ''
        }
        return redirect('/')

    redirect_uri = url_for('auth_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback from Google."""
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')

        if not user_info:
            return redirect('/?error=no_user_info')

        email = user_info.get('email', '').lower()
        if not email.endswith(f'@{ALLOWED_DOMAIN}'):
            return redirect('/?error=invalid_domain')

        session['user'] = {
            'email': email,
            'name': user_info.get('name', ''),
            'picture': user_info.get('picture', '')
        }

        return redirect('/')

    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return redirect('/?error=auth_failed')


@app.route('/logout')
def logout():
    """Log out the current user."""
    session.clear()
    return redirect('/')


@app.route('/api/auth/status')
def auth_status():
    """Check authentication status."""
    if DEV_MODE:
        return jsonify({
            'authenticated': True,
            'user': {
                'email': DEV_USER_EMAIL,
                'name': 'Dev User',
                'picture': ''
            },
            'isAdmin': True,
            'isTalent': True
        })

    user = session.get('user')
    if user:
        email = user.get('email', '').lower()

        # Look up job title to determine role-based access
        is_talent = False
        has_access = False
        job_title = session.get('job_title', '')

        # Cache job title in session to avoid repeated BigQuery lookups
        if not job_title and bq_client:
            try:
                query = f"""
                    SELECT Job_Title
                    FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
                    WHERE LOWER(TRIM(Email_Address)) = @email
                    LIMIT 1
                """
                params = [bigquery.ScalarQueryParameter("email", "STRING", email)]
                job_config = bigquery.QueryJobConfig(query_parameters=params)
                rows = list(bq_client.query(query, job_config=job_config).result())
                if rows:
                    job_title = (rows[0].Job_Title or '').strip()
                    session['job_title'] = job_title
            except Exception as e:
                logger.error(f"Error looking up job title: {e}")

        if job_title:
            is_talent = job_title in TALENT_TITLES
            has_access = has_staffing_board_access(job_title)

        return jsonify({
            'authenticated': True,
            'user': user,
            'hasAccess': has_access,
            'isTalent': is_talent
        })

    return jsonify({'authenticated': False})


# ─────────────────────────────────────────────────────────────────────────────
# Static Files
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the Position Control dashboard."""
    return send_from_directory(HTML_DIR, 'index.html')


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'position-control'})


# ─────────────────────────────────────────────────────────────────────────────
# Position Control API
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/positions')
@login_required
def get_positions():
    """
    Get all positions with optional filters.
    Query params: school, category, status, status26, search
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    school_filter = request.args.get('school', '')
    category_filter = request.args.get('category', '')
    status_filter = request.args.get('status', '')
    status26_filter = request.args.get('status26', '')
    search_term = request.args.get('search', '')

    try:
        query = f"""
            SELECT
                p.position_id,
                TRIM(p.school) as school,
                p.job_category,
                p.job_title,
                p.subject,
                p.grade_level,
                p.staffing_matrix,
                p.current_status,
                p.first_name,
                p.last_name,
                p.employee_25_26,
                p.email_address,
                p.employee_number,
                p.validation,
                p.employee_26_27,
                p.employee_number_26_27,
                p.status_26_27,
                p.itr_response,
                p.notes,
                p.start_year,
                p.end_year,
                -- HR data
                CASE
                    WHEN sml.Employment_Status IS NOT NULL THEN sml.Employment_Status
                    ELSE 'Unknown'
                END as hr_status,
                sml.Supervisor_Name__Unsecured_ as supervisor,
                sml.Subject_Desc as hr_subject,
                sml.Job_Title as hr_job_title,
                sml.Grade_Level_Desc as hr_grade_level,
                sml.Location_Name as hr_location,
                sml.Job_Function as hr_job_function,
                -- Mismatch flags (only for active positions with employees)
                CASE WHEN p.current_status = 'Active' AND p.email_address IS NOT NULL AND p.email_address != '' THEN
                    CASE WHEN sml.Email_Address IS NULL THEN TRUE ELSE FALSE END
                ELSE FALSE END as flag_not_in_hr,
                CASE WHEN p.current_status = 'Active' AND sml.Employment_Status IS NOT NULL AND sml.Employment_Status NOT IN ('Active', 'Leave of absence') THEN TRUE ELSE FALSE END as flag_status_mismatch,
                CASE WHEN p.current_status = 'Active' AND sml.Subject_Desc IS NOT NULL AND LOWER(TRIM(COALESCE(p.subject, ''))) != LOWER(TRIM(sml.Subject_Desc)) AND p.subject IS NOT NULL AND p.subject != '' THEN TRUE ELSE FALSE END as flag_subject_mismatch,
                CASE WHEN p.current_status = 'Active' AND sml.Job_Title IS NOT NULL AND LOWER(TRIM(p.job_title)) != LOWER(TRIM(sml.Job_Title)) THEN TRUE ELSE FALSE END as flag_title_mismatch,
                CASE WHEN p.current_status = 'Active' AND sml.Location_Name IS NOT NULL AND p.school !=
                    CASE
                        WHEN sml.Location_Name = 'Arthur Ashe Charter School' THEN 'Arthur Ashe'
                        WHEN sml.Location_Name = 'Langston Hughes Academy' THEN 'Langston Hughes'
                        WHEN sml.Location_Name = 'Phillis Wheatley Community School' THEN 'Phillis Wheatley'
                        WHEN sml.Location_Name = 'Samuel J Green Charter School' THEN 'Samuel J Green'
                        WHEN sml.Location_Name = 'FirstLine Network' THEN 'Network'
                        WHEN sml.Location_Name LIKE 'FLS%' THEN 'Network'
                        ELSE sml.Location_Name
                    END
                THEN TRUE ELSE FALSE END as flag_location_mismatch
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}` p
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(TRIM(p.email_address)) = LOWER(TRIM(sml.Email_Address))
            WHERE 1=1
                {"AND TRIM(p.school) = @school" if school_filter else ""}
                {"AND p.job_category = @category" if category_filter else ""}
                {"AND p.current_status = @status" if status_filter else ""}
                {"AND p.status_26_27 = @status26" if status26_filter else ""}
                {"AND (LOWER(p.first_name) LIKE @search OR LOWER(p.last_name) LIKE @search OR LOWER(p.job_title) LIKE @search OR LOWER(p.subject) LIKE @search OR LOWER(p.school) LIKE @search)" if search_term else ""}
            ORDER BY p.school, p.job_category, p.job_title
        """

        params = []
        if school_filter:
            params.append(bigquery.ScalarQueryParameter("school", "STRING", school_filter))
        if category_filter:
            params.append(bigquery.ScalarQueryParameter("category", "STRING", category_filter))
        if status_filter:
            params.append(bigquery.ScalarQueryParameter("status", "STRING", status_filter))
        if status26_filter:
            params.append(bigquery.ScalarQueryParameter("status26", "STRING", status26_filter))
        if search_term:
            params.append(bigquery.ScalarQueryParameter("search", "STRING", f"%{search_term.lower()}%"))

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = bq_client.query(query, job_config=job_config).result()

        positions = []
        for row in results:
            position = dict(row.items())
            positions.append(position)

        logger.info(f"Fetched {len(positions)} positions")
        return jsonify(positions)

    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/stats')
@login_required
def get_position_stats():
    """Get aggregate statistics for positions."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    # Optional year filter - defaults to showing all
    year = request.args.get('year', '')

    try:
        # Build year filter clause
        year_clause = ""
        if year:
            year_clause = f"WHERE {year_filter_sql(year)}"

        query = f"""
            SELECT
                COUNTIF(current_status NOT IN ('Not Filling Seat', 'Overhire')) as total,
                COUNTIF(current_status = 'Active') as active,
                COUNTIF(current_status = 'Overhire') as overhire,
                COUNTIF(current_status = 'Filled') as onboarding,
                COUNTIF(current_status IN ('Open', 'Finalist')) as open_25,
                COUNTIF(status_26_27 = 'Return') as returning,
                COUNTIF(status_26_27 = 'Possible Open') as possible_open,
                COUNTIF(status_26_27 = 'Open') as open_26,
                COUNTIF(status_26_27 = 'Filled') as filled_26,
                COUNTIF(status_26_27 = 'Seat Change') as seat_change,
                COUNTIF(itr_response = 'Yes') as itr_yes,
                COUNTIF(itr_response = 'Unsure') as itr_unsure,
                COUNTIF(itr_response = 'No') as itr_no,
                COUNTIF(itr_response = 'No response yet') as itr_no_response,
                COUNTIF(itr_response = 'Open seat') as itr_open_seat,
                COUNTIF(itr_response = 'New hire' OR itr_response = 'New Hire') as itr_new_hire,
                COUNTIF(itr_response = 'Leave') as itr_leave
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            {year_clause}
        """

        results = bq_client.query(query).result()
        row = list(results)[0]
        stats = dict(row.items())

        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error fetching position stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/by-school')
@login_required
def get_positions_by_school():
    """Get position statistics grouped by school."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    # Optional year filter
    year = request.args.get('year', '')

    try:
        # Build year filter clause
        year_clause = ""
        if year:
            year_clause = f"WHERE {year_filter_sql(year)}"

        query = f"""
            SELECT
                school,
                COUNTIF(current_status NOT IN ('Not Filling Seat', 'Overhire')) as total,
                COUNTIF(current_status = 'Active') as active,
                COUNTIF(current_status = 'Overhire') as overhire,
                COUNTIF(current_status = 'Filled') as onboarding,
                COUNTIF(current_status IN ('Open', 'Finalist')) as open_25,
                COUNTIF(status_26_27 = 'Return') as returning,
                COUNTIF(status_26_27 = 'Possible Open') as possible_open,
                COUNTIF(status_26_27 = 'Open') as open_26,
                -- Teacher counts
                COUNTIF(job_category = 'Teacher' AND current_status NOT IN ('Not Filling Seat', 'Overhire')) as teachers,
                COUNTIF(job_category = 'Teacher' AND current_status = 'Active') as teachers_active,
                COUNTIF(job_category = 'Teacher' AND current_status = 'Filled') as teachers_onboarding,
                COUNTIF(job_category = 'Teacher' AND current_status IN ('Open', 'Finalist')) as teachers_open,
                -- Support counts
                COUNTIF(job_category = 'Support' AND current_status NOT IN ('Not Filling Seat', 'Overhire')) as support,
                COUNTIF(job_category = 'Support' AND current_status = 'Active') as support_active,
                COUNTIF(job_category = 'Support' AND current_status = 'Filled') as support_onboarding,
                COUNTIF(job_category = 'Support' AND current_status IN ('Open', 'Finalist')) as support_open,
                -- Leadership counts
                COUNTIF(job_category = 'Leadership' AND current_status NOT IN ('Not Filling Seat', 'Overhire')) as leadership,
                COUNTIF(job_category = 'Leadership' AND current_status = 'Active') as leadership_active,
                COUNTIF(job_category = 'Leadership' AND current_status = 'Filled') as leadership_onboarding,
                COUNTIF(job_category = 'Leadership' AND current_status IN ('Open', 'Finalist')) as leadership_open,
                -- Operations counts
                COUNTIF(job_category = 'Operations' AND current_status NOT IN ('Not Filling Seat', 'Overhire')) as operations,
                COUNTIF(job_category = 'Operations' AND current_status = 'Active') as operations_active,
                COUNTIF(job_category = 'Operations' AND current_status = 'Filled') as operations_onboarding,
                COUNTIF(job_category = 'Operations' AND current_status IN ('Open', 'Finalist')) as operations_open
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            {year_clause}
            GROUP BY school
            ORDER BY school
        """

        results = bq_client.query(query).result()

        schools = []
        for row in results:
            school_data = dict(row.items())
            total = school_data['total']
            active = school_data['active']
            # pct_staffed based on active (fully onboarded) employees
            school_data['pct_staffed'] = round((active / total * 100), 1) if total > 0 else 0
            schools.append(school_data)

        return jsonify(schools)

    except Exception as e:
        logger.error(f"Error fetching positions by school: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/job-options')
@login_required
def get_job_options():
    """
    Get job titles, subjects, and grade levels from HR system for dropdowns.
    Includes Job Function mapping for auto-populating Category.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Get job titles with their job functions
        job_query = f"""
            SELECT DISTINCT Job_Title, Job_Function
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE Job_Title IS NOT NULL AND Job_Title != ''
            ORDER BY Job_Title
        """
        job_results = bq_client.query(job_query).result()
        job_titles = []
        job_function_map = {}
        for row in job_results:
            job_titles.append(row.Job_Title)
            job_function_map[row.Job_Title] = row.Job_Function or ''

        # Get subjects
        subject_query = f"""
            SELECT DISTINCT Subject_Desc
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE Subject_Desc IS NOT NULL AND Subject_Desc != ''
            ORDER BY Subject_Desc
        """
        subject_results = bq_client.query(subject_query).result()
        subjects = [row.Subject_Desc for row in subject_results]

        # Get grade levels
        grade_query = f"""
            SELECT DISTINCT Grade_Level_Desc
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE Grade_Level_Desc IS NOT NULL AND Grade_Level_Desc != ''
            ORDER BY Grade_Level_Desc
        """
        grade_results = bq_client.query(grade_query).result()
        grade_levels = [row.Grade_Level_Desc for row in grade_results]

        # Get active employees for 26-27 autocomplete
        emp_query = f"""
            SELECT DISTINCT
                CONCAT(First_Name, ' ', Last_Name) as name,
                Employee_Number
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE Employment_Status IN ('Active', 'Leave of absence')
              AND First_Name IS NOT NULL AND Last_Name IS NOT NULL
            ORDER BY name
        """
        emp_results = bq_client.query(emp_query).result()
        employees_26 = [{'name': row.name, 'employee_number': row.Employee_Number} for row in emp_results]

        return jsonify({
            'job_titles': job_titles,
            'job_function_map': job_function_map,
            'subjects': subjects,
            'grade_levels': grade_levels,
            'categories': ['Leadership', 'Teacher', 'Support', 'Operations', 'Network'],
            'employees_26': employees_26,
        })

    except Exception as e:
        logger.error(f"Error fetching job options: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/filter-options')
@login_required
def get_filter_options():
    """Get available filter options."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT DISTINCT
                TRIM(school) as school,
                job_category,
                current_status,
                status_26_27,
                itr_response,
                staffing_matrix
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            WHERE school IS NOT NULL AND TRIM(school) != ''
        """

        results = bq_client.query(query).result()

        schools = set()
        categories = set()
        statuses = set()
        statuses_26 = set()
        valid_26_statuses = {'Return', 'Possible Open', 'Open', 'Finalist', 'Offer Out', 'Filled', 'Seat Change', 'Not Filling Seat'}
        itr_responses = set()
        matrices = set()

        for row in results:
            if row.school and row.school.strip():
                schools.add(row.school.strip())
            if row.job_category:
                categories.add(row.job_category)
            if row.current_status:
                statuses.add(row.current_status)
            if row.status_26_27 and row.status_26_27 in valid_26_statuses:
                statuses_26.add(row.status_26_27)
            if row.itr_response:
                itr_responses.add(row.itr_response)
            if row.staffing_matrix:
                matrices.add(row.staffing_matrix)

        return jsonify({
            'schools': sorted(list(schools)),
            'categories': sorted(list(categories)),
            'statuses': sorted(list(statuses)),
            'statuses_26': sorted(list(statuses_26)),
            'itr_responses': sorted(list(itr_responses)),
            'matrices': sorted(list(matrices)),
            'school_years': SCHOOL_YEARS
        })

    except Exception as e:
        logger.error(f"Error fetching filter options: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/action-needed')
@login_required
def get_action_needed():
    """Get positions that need action for 26-27 (Open or Possible Open)."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Only show positions that apply to 26-27
        query = f"""
            SELECT
                school,
                job_category,
                job_title,
                subject,
                grade_level,
                employee_25_26,
                email_address,
                status_26_27,
                itr_response
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            WHERE status_26_27 IN ('Open', 'Possible Open')
                AND {year_filter_sql('26-27')}
            ORDER BY
                CASE WHEN status_26_27 = 'Open' THEN 0 ELSE 1 END,
                school,
                job_category,
                job_title
        """

        results = bq_client.query(query).result()

        positions = []
        for row in results:
            positions.append(dict(row.items()))

        return jsonify(positions)

    except Exception as e:
        logger.error(f"Error fetching action needed positions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reconciliation')
@login_required
def get_reconciliation():
    """
    Reconcile position data against active staff list.
    Returns positions with mismatched data.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                p.school,
                p.job_title,
                p.employee_25_26 as position_employee,
                p.email_address as position_email,
                p.current_status as position_status,
                s.first_name || ' ' || s.last_name as hr_employee,
                s.Email_Address as hr_email,
                s.Employment_Status as hr_status,
                -- Normalize HR location names to match position school names
                CASE
                    WHEN s.Location_Name = 'Arthur Ashe Charter School' THEN 'Arthur Ashe'
                    WHEN s.Location_Name = 'Langston Hughes Academy' THEN 'Langston Hughes'
                    WHEN s.Location_Name = 'Phillis Wheatley Community School' THEN 'Phillis Wheatley'
                    WHEN s.Location_Name = 'Samuel J Green Charter School' THEN 'Samuel J Green'
                    WHEN s.Location_Name = 'FirstLine Network' THEN 'Network'
                    WHEN s.Location_Name LIKE 'FLS%' THEN 'Network'
                    ELSE s.Location_Name
                END as hr_location,
                CASE
                    WHEN s.Email_Address IS NULL THEN 'Not in HR System'
                    WHEN s.Employment_Status != 'Active' AND p.current_status = 'Active' THEN 'Status Mismatch'
                    WHEN LOWER(TRIM(p.employee_25_26)) != LOWER(TRIM(s.first_name || ' ' || s.last_name)) THEN 'Name Mismatch'
                    WHEN p.school != CASE
                        WHEN s.Location_Name = 'Arthur Ashe Charter School' THEN 'Arthur Ashe'
                        WHEN s.Location_Name = 'Langston Hughes Academy' THEN 'Langston Hughes'
                        WHEN s.Location_Name = 'Phillis Wheatley Community School' THEN 'Phillis Wheatley'
                        WHEN s.Location_Name = 'Samuel J Green Charter School' THEN 'Samuel J Green'
                        WHEN s.Location_Name = 'FirstLine Network' THEN 'Network'
                        WHEN s.Location_Name LIKE 'FLS%' THEN 'Network'
                        ELSE s.Location_Name
                    END THEN 'Location Mismatch'
                    ELSE 'OK'
                END as reconciliation_status
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}` p
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{STAFF_TABLE}` s
                ON LOWER(TRIM(p.email_address)) = LOWER(TRIM(s.Email_Address))
            WHERE p.current_status = 'Active'
            ORDER BY
                CASE
                    WHEN s.Email_Address IS NULL THEN 0
                    WHEN s.Employment_Status != 'Active' THEN 1
                    ELSE 2
                END,
                p.school,
                p.job_title
        """

        results = bq_client.query(query).result()

        mismatches = []
        for row in results:
            data = dict(row.items())
            if data['reconciliation_status'] != 'OK':
                mismatches.append(data)

        return jsonify({
            'total_mismatches': len(mismatches),
            'mismatches': mismatches
        })

    except Exception as e:
        logger.error(f"Error running reconciliation: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# CRUD Operations
# ─────────────────────────────────────────────────────────────────────────────

HISTORY_TABLE = "position_history"


@app.route('/api/positions/<position_id>', methods=['GET'])
@login_required
def get_position(position_id):
    """Get a single position by ID."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            WHERE position_id = @position_id
        """
        params = [bigquery.ScalarQueryParameter("position_id", "STRING", position_id)]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        if not results:
            return jsonify({'error': 'Position not found'}), 404

        position = dict(results[0].items())
        # Convert timestamps to ISO format
        for key in ['created_at', 'updated_at']:
            if position.get(key):
                position[key] = position[key].isoformat()

        return jsonify(position)

    except Exception as e:
        logger.error(f"Error fetching position: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/<position_id>', methods=['PUT'])
@login_required
def update_position(position_id):
    """Update a position."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user = session.get('user', {})
    user_email = user.get('email', 'unknown')

    try:
        # Get current position for history
        query = f"""
            SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            WHERE position_id = @position_id
        """
        params = [bigquery.ScalarQueryParameter("position_id", "STRING", position_id)]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = list(bq_client.query(query, job_config=job_config).result())

        if not results:
            return jsonify({'error': 'Position not found'}), 404

        old_position = dict(results[0].items())

        # Build update query
        editable_fields = [
            'school', 'job_category', 'job_title', 'subject', 'grade_level',
            'staffing_matrix', 'current_status', 'first_name', 'last_name',
            'employee_25_26', 'email_address', 'employee_number', 'validation',
            'employee_26_27', 'employee_number_26_27', 'status_26_27', 'itr_response', 'notes', 'candidate_name',
            'start_year', 'end_year'
        ]

        updates = []
        history_records = []
        from datetime import datetime
        import uuid
        now = datetime.utcnow().isoformat()

        for field in editable_fields:
            if field in data and data[field] != old_position.get(field):
                updates.append(f"{field} = @{field}")
                # Record change in history
                history_records.append({
                    "history_id": str(uuid.uuid4()),
                    "position_id": position_id,
                    "action": "UPDATE",
                    "field_changed": field,
                    "old_value": str(old_position.get(field, '')),
                    "new_value": str(data[field]),
                    "changed_by": user_email,
                    "changed_at": now,
                })

        if not updates:
            return jsonify({'message': 'No changes detected'})

        updates.append("updated_at = @updated_at")
        updates.append("updated_by = @updated_by")

        update_query = f"""
            UPDATE `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            SET {', '.join(updates)}
            WHERE position_id = @position_id
        """

        params = [bigquery.ScalarQueryParameter("position_id", "STRING", position_id)]
        params.append(bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", now))
        params.append(bigquery.ScalarQueryParameter("updated_by", "STRING", user_email))

        for field in editable_fields:
            if field in data:
                params.append(bigquery.ScalarQueryParameter(field, "STRING", str(data[field]) if data[field] else ""))

        job_config = bigquery.QueryJobConfig(query_parameters=params)
        bq_client.query(update_query, job_config=job_config).result()

        # Insert history records
        if history_records:
            history_table_id = f"{PROJECT_ID}.{DATASET_ID}.{HISTORY_TABLE}"
            bq_client.insert_rows_json(history_table_id, history_records)

        logger.info(f"Updated position {position_id} by {user_email}")
        return jsonify({'message': 'Position updated successfully', 'changes': len(history_records)})

    except Exception as e:
        logger.error(f"Error updating position: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions', methods=['POST'])
@login_required
def create_position():
    """Create a new position."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user = session.get('user', {})
    user_email = user.get('email', 'unknown')

    try:
        from datetime import datetime
        import uuid

        now = datetime.utcnow().isoformat()
        position_id = str(uuid.uuid4())

        row = {
            "position_id": position_id,
            "school": data.get("school", ""),
            "job_category": data.get("job_category", ""),
            "job_title": data.get("job_title", ""),
            "subject": data.get("subject", ""),
            "grade_level": data.get("grade_level", ""),
            "staffing_matrix": data.get("staffing_matrix", ""),
            "current_status": data.get("current_status", "Open"),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "employee_25_26": data.get("employee_25_26", ""),
            "email_address": data.get("email_address", ""),
            "employee_number": data.get("employee_number", ""),
            "validation": data.get("validation", ""),
            "employee_26_27": data.get("employee_26_27", ""),
            "employee_number_26_27": data.get("employee_number_26_27", ""),
            "status_26_27": data.get("status_26_27", "Open"),
            "itr_response": data.get("itr_response", ""),
            "notes": data.get("notes", ""),
            "candidate_name": data.get("candidate_name", ""),
            "start_year": data.get("start_year", "25-26"),
            "end_year": data.get("end_year", None),
            "created_at": now,
            "updated_at": now,
            "updated_by": user_email,
        }

        table_id = f"{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}"
        errors = bq_client.insert_rows_json(table_id, [row])

        if errors:
            return jsonify({'error': f'Failed to create position: {errors}'}), 500

        # Log creation in history
        history_table_id = f"{PROJECT_ID}.{DATASET_ID}.{HISTORY_TABLE}"
        bq_client.insert_rows_json(history_table_id, [{
            "history_id": str(uuid.uuid4()),
            "position_id": position_id,
            "action": "CREATE",
            "field_changed": "",
            "old_value": "",
            "new_value": f"{data.get('job_title', '')} at {data.get('school', '')}",
            "changed_by": user_email,
            "changed_at": now,
        }])

        logger.info(f"Created position {position_id} by {user_email}")
        return jsonify({'message': 'Position created', 'position_id': position_id}), 201

    except Exception as e:
        logger.error(f"Error creating position: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/<position_id>', methods=['DELETE'])
@login_required
def delete_position(position_id):
    """Delete a position."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', 'unknown')

    try:
        from datetime import datetime
        import uuid

        # Log deletion in history first
        now = datetime.utcnow().isoformat()
        history_table_id = f"{PROJECT_ID}.{DATASET_ID}.{HISTORY_TABLE}"
        bq_client.insert_rows_json(history_table_id, [{
            "history_id": str(uuid.uuid4()),
            "position_id": position_id,
            "action": "DELETE",
            "field_changed": "",
            "old_value": "",
            "new_value": "",
            "changed_by": user_email,
            "changed_at": now,
        }])

        # Delete position
        query = f"""
            DELETE FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            WHERE position_id = @position_id
        """
        params = [bigquery.ScalarQueryParameter("position_id", "STRING", position_id)]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        bq_client.query(query, job_config=job_config).result()

        logger.info(f"Deleted position {position_id} by {user_email}")
        return jsonify({'message': 'Position deleted'})

    except Exception as e:
        logger.error(f"Error deleting position: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/positions/<position_id>/history')
@login_required
def get_position_history(position_id):
    """Get change history for a position."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{HISTORY_TABLE}`
            WHERE position_id = @position_id
            ORDER BY changed_at DESC
        """
        params = [bigquery.ScalarQueryParameter("position_id", "STRING", position_id)]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = bq_client.query(query, job_config=job_config).result()

        history = []
        for row in results:
            record = dict(row.items())
            if record.get('changed_at'):
                record['changed_at'] = record['changed_at'].isoformat()
            history.append(record)

        return jsonify(history)

    except Exception as e:
        logger.error(f"Error fetching position history: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Unassigned Staff (in HR but not in Position Control)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/unassigned-staff')
@login_required
def get_unassigned_staff():
    """
    Get employees from HR system who are not assigned to any position.
    These are people with EIDs in staff_master_list but no matching email in position_control.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                sml.Employee_Number as employee_id,
                sml.first_name,
                sml.last_name,
                sml.Email_Address as email,
                sml.Job_Title as job_title,
                sml.Subject_Desc as subject,
                sml.Grade_Level_Desc as grade_level,
                sml.Employment_Status as status,
                CASE
                    WHEN sml.Location_Name = 'Arthur Ashe Charter School' THEN 'Arthur Ashe'
                    WHEN sml.Location_Name = 'Langston Hughes Academy' THEN 'Langston Hughes'
                    WHEN sml.Location_Name = 'Phillis Wheatley Community School' THEN 'Phillis Wheatley'
                    WHEN sml.Location_Name = 'Samuel J Green Charter School' THEN 'Samuel J Green'
                    WHEN sml.Location_Name = 'FirstLine Network' THEN 'Network'
                    WHEN sml.Location_Name LIKE 'FLS%' THEN 'Network'
                    ELSE sml.Location_Name
                END as location,
                sml.Job_Function as job_function
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}` p
                ON LOWER(TRIM(sml.Email_Address)) = LOWER(TRIM(p.email_address))
            WHERE sml.Employment_Status = 'Active'
                AND p.position_id IS NULL
            ORDER BY sml.Location_Name, sml.last_name, sml.first_name
        """

        results = bq_client.query(query).result()

        staff = []
        for row in results:
            staff.append(dict(row.items()))

        return jsonify({
            'count': len(staff),
            'staff': staff
        })

    except Exception as e:
        logger.error(f"Error fetching unassigned staff: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding Matches (Filled positions with likely HRIS matches)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/onboarding-matches')
@login_required
def get_onboarding_matches():
    """
    Find Filled positions where the employee name matches an Active, unassigned
    HRIS employee. Returns suggestions for the talent team to review and link.
    Name matching is used only as a suggestion — no automatic changes are made.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                p.position_id,
                p.employee_25_26 as position_name,
                p.school as position_school,
                p.job_title as position_title,
                sml.First_Name as hr_first_name,
                sml.Last_Name as hr_last_name,
                sml.Email_Address as hr_email,
                sml.Employee_Number as hr_employee_id,
                sml.Job_Title as hr_title,
                CASE
                    WHEN sml.Location_Name = 'Arthur Ashe Charter School' THEN 'Arthur Ashe'
                    WHEN sml.Location_Name = 'Langston Hughes Academy' THEN 'Langston Hughes'
                    WHEN sml.Location_Name = 'Phillis Wheatley Community School' THEN 'Phillis Wheatley'
                    WHEN sml.Location_Name = 'Samuel J Green Charter School' THEN 'Samuel J Green'
                    WHEN sml.Location_Name = 'FirstLine Network' THEN 'Network'
                    WHEN sml.Location_Name LIKE 'FLS%' THEN 'Network'
                    ELSE sml.Location_Name
                END as hr_location
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}` p
            INNER JOIN `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` sml
                ON LOWER(REGEXP_REPLACE(TRIM(p.employee_25_26), r'\\s+', ' ')) = LOWER(TRIM(CONCAT(sml.First_Name, ' ', sml.Last_Name)))
            LEFT JOIN `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}` p2
                ON LOWER(TRIM(sml.Email_Address)) = LOWER(TRIM(p2.email_address))
            WHERE p.current_status = 'Filled'
                AND p.employee_25_26 IS NOT NULL
                AND p.employee_25_26 != ''
                AND sml.Employment_Status = 'Active'
                AND p2.position_id IS NULL
            ORDER BY p.school, p.employee_25_26
        """

        results = bq_client.query(query).result()

        matches = []
        for row in results:
            matches.append({
                'position_id': row.position_id,
                'position_name': row.position_name,
                'position_school': row.position_school,
                'position_title': row.position_title,
                'hr_name': f"{row.hr_first_name} {row.hr_last_name}",
                'hr_email': row.hr_email,
                'hr_employee_id': row.hr_employee_id,
                'hr_title': row.hr_title,
                'hr_location': row.hr_location,
            })

        logger.info(f"Found {len(matches)} onboarding matches")
        return jsonify({
            'count': len(matches),
            'matches': matches
        })

    except Exception as e:
        logger.error(f"Error fetching onboarding matches: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Hiring Summary
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/hiring-summary')
@login_required
def get_hiring_summary():
    """
    Get hiring goal summary by school and category.
    Shows: Remaining to Hire, Hired to Date, Total to Hire, % to Goal, % Staffed
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Define site schools
        site_schools = ['Arthur Ashe', 'Samuel J Green', 'Langston Hughes', 'Phillis Wheatley']

        query = f"""
            SELECT
                school,
                job_category,
                COUNTIF(current_status != 'Not Filling Seat') as total_positions,
                COUNTIF(current_status = 'Active') as filled_positions,
                COUNTIF(status_26_27 IN ('Open', 'Possible Open')) as positions_to_hire,
                COUNTIF(status_26_27 = 'Filled') as hired_to_date
            FROM `{PROJECT_ID}.{DATASET_ID}.{POSITION_TABLE}`
            WHERE school IN UNNEST(@schools)
                AND {year_filter_sql('26-27')}
            GROUP BY school, job_category
        """

        params = [bigquery.ArrayQueryParameter("schools", "STRING", site_schools)]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        results = bq_client.query(query, job_config=job_config).result()

        # Build summary structure
        categories = ['Leadership', 'Teacher', 'Support', 'Operations']
        summary = {}

        for school in site_schools:
            summary[school] = {cat: {'total': 0, 'filled': 0, 'to_hire': 0, 'hired': 0} for cat in categories}
            summary[school]['All'] = {'total': 0, 'filled': 0, 'to_hire': 0, 'hired': 0}

        summary['ALL SCHOOLS'] = {cat: {'total': 0, 'filled': 0, 'to_hire': 0, 'hired': 0} for cat in categories}
        summary['ALL SCHOOLS']['All'] = {'total': 0, 'filled': 0, 'to_hire': 0, 'hired': 0}

        for row in results:
            school = row.school
            cat = row.job_category if row.job_category in categories else None

            if school in summary and cat:
                summary[school][cat]['total'] += row.total_positions
                summary[school][cat]['filled'] += row.filled_positions
                summary[school][cat]['to_hire'] += row.positions_to_hire
                summary[school][cat]['hired'] += row.hired_to_date

                summary[school]['All']['total'] += row.total_positions
                summary[school]['All']['filled'] += row.filled_positions
                summary[school]['All']['to_hire'] += row.positions_to_hire
                summary[school]['All']['hired'] += row.hired_to_date

                summary['ALL SCHOOLS'][cat]['total'] += row.total_positions
                summary['ALL SCHOOLS'][cat]['filled'] += row.filled_positions
                summary['ALL SCHOOLS'][cat]['to_hire'] += row.positions_to_hire
                summary['ALL SCHOOLS'][cat]['hired'] += row.hired_to_date

                summary['ALL SCHOOLS']['All']['total'] += row.total_positions
                summary['ALL SCHOOLS']['All']['filled'] += row.filled_positions
                summary['ALL SCHOOLS']['All']['to_hire'] += row.positions_to_hire
                summary['ALL SCHOOLS']['All']['hired'] += row.hired_to_date

        # Calculate percentages
        result = []
        for school in site_schools + ['ALL SCHOOLS']:
            row_data = {'school': school}
            for cat in ['All'] + categories:
                data = summary[school][cat]
                total_to_hire = data['to_hire'] + data['hired']
                remaining = data['to_hire']
                hired = data['hired']
                pct_goal = round((hired / total_to_hire * 100), 0) if total_to_hire > 0 else None
                pct_staffed = round((data['filled'] / data['total'] * 100), 0) if data['total'] > 0 else None

                row_data[cat] = {
                    'remaining': remaining,
                    'hired': hired,
                    'total_to_hire': total_to_hire,
                    'pct_goal': pct_goal,
                    'pct_staffed': pct_staffed,
                }
            result.append(row_data)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching hiring summary: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not bq_client:
        logger.warning("BigQuery client is not initialized. Please check your credentials.")
        logger.warning("Run: gcloud auth application-default login")

    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'

    logger.info(f"Starting Position Control on http://localhost:{port}")
    app.run(debug=debug_mode, port=port, host='0.0.0.0')
