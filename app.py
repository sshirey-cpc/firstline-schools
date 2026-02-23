#!/usr/bin/env python3
"""
Intent to Return Dashboard - Dynamic Flask App
Provides real-time ITR data with year-over-year comparison.
"""

from functools import wraps
from flask import Flask, jsonify, send_file, redirect, url_for, session, request
from google.cloud import bigquery
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
import os
import secrets

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Session configuration
app.secret_key = os.environ.get('SECRET_KEY') or os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'development'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = "talent-demo-482004"
ALLOWED_DOMAIN = 'firstlineschools.org'
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
DEV_MODE = os.environ.get('FLASK_ENV') == 'development' or not GOOGLE_CLIENT_ID
DEV_USER_EMAIL = 'sshirey@firstlineschools.org'

# OAuth setup
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# Initialize BigQuery client
try:
    client = bigquery.Client(project=PROJECT_ID)
    logger.info("BigQuery client initialized")
except Exception as e:
    logger.error(f"Failed to initialize BigQuery client: {e}")
    client = None


def login_required(f):
    """Decorator to require authentication on routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated

# Site name mapping between years
SITE_MAPPING = {
    'Arthur Ashe': 'Arthur Ashe Charter School',
    'Langston Hughes Academy': 'Langston Hughes Academy',
    'Phillis Wheatley': 'Phillis Wheatley Community School',
    'Samuel J Green': 'Samuel J Green Charter School',
    'FirstLine Network': 'FirstLine Network'
}

# Job function mapping between years
FUNCTION_MAPPING = {
    'Leader': 'Leadership',
    'Network': 'Network',
    'Operations': 'Operations',
    'Support': 'Support',
    'Teacher': 'Teacher'
}


@app.route('/')
def index():
    """Serve the main dashboard page."""
    return send_file('index.html')


@app.route('/login')
def login():
    """Initiate Google OAuth flow."""
    if DEV_MODE:
        logger.info(f"DEV MODE: Auto-authenticating as {DEV_USER_EMAIL}")
        session['user'] = {'email': DEV_USER_EMAIL, 'name': 'Dev User'}
        return redirect('/')
    google = oauth.create_client('google')
    redirect_uri = url_for('auth_callback', _external=True)
    # Force new-format Cloud Run URL so OAuth callback matches registered URI
    redirect_uri = redirect_uri.replace('daem7b6ydq-uc.a.run.app', '965913991496.us-central1.run.app')
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback from Google."""
    try:
        google = oauth.create_client('google')
        token = google.authorize_access_token()
        userinfo = token.get('userinfo')
        if not userinfo:
            return redirect('/?error=auth_failed')
        email = userinfo.get('email', '')
        domain = email.split('@')[-1] if '@' in email else ''
        if domain.lower() != ALLOWED_DOMAIN.lower():
            logger.warning(f"Unauthorized domain attempt: {email}")
            return redirect(f'/?error=unauthorized_domain&domain={domain}')
        session['user'] = {
            'email': email,
            'name': userinfo.get('name', ''),
            'picture': userinfo.get('picture', ''),
        }
        logger.info(f"User authenticated: {email}")
        return redirect('/')
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return redirect('/?error=auth_failed')


@app.route('/logout')
def logout():
    """Clear session and log out user."""
    session.clear()
    return redirect('/')


@app.route('/api/auth/status')
def auth_status():
    """Return current authentication status."""
    if 'user' in session:
        return jsonify({'authenticated': True, 'user': session['user']})
    return jsonify({'authenticated': False, 'user': None})


@app.route('/api/current-year')
@login_required
def get_current_year():
    """Get current year (2025-26) ITR data."""
    if not client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Overall summary
        overall_query = """
        SELECT
            COUNT(*) as total_staff,
            SUM(CASE WHEN i.Return IS NOT NULL THEN 1 ELSE 0 END) as responded,
            SUM(CASE WHEN i.Return = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN i.Return = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN i.Return = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS)), 1) as avg_nps,
            SUM(CASE WHEN COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) >= 9 THEN 1 ELSE 0 END) as promoters,
            SUM(CASE WHEN COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) BETWEEN 7 AND 8 THEN 1 ELSE 0 END) as passives,
            SUM(CASE WHEN COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) <= 6 AND COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) IS NOT NULL THEN 1 ELSE 0 END) as detractors,
            SUM(CASE WHEN COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) IS NOT NULL THEN 1 ELSE 0 END) as nps_respondents
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        LEFT JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        """

        # By location
        location_query = """
        SELECT
            s.Location_Name as name,
            COUNT(*) as total_staff,
            SUM(CASE WHEN i.Return IS NOT NULL THEN 1 ELSE 0 END) as responded,
            SUM(CASE WHEN i.Return = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN i.Return = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN i.Return = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS)), 1) as avg_nps
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        LEFT JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        GROUP BY s.Location_Name
        ORDER BY s.Location_Name
        """

        # By role
        role_query = """
        SELECT
            s.Job_Function as name,
            COUNT(*) as total_staff,
            SUM(CASE WHEN i.Return IS NOT NULL THEN 1 ELSE 0 END) as responded,
            SUM(CASE WHEN i.Return = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN i.Return = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN i.Return = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS)), 1) as avg_nps
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        LEFT JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        GROUP BY s.Job_Function
        ORDER BY s.Job_Function
        """

        # By tenure (using school-year based calculation)
        tenure_query = """
        WITH staff_with_tenure AS (
            SELECT
                s.*,
                i.Return,
                COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) as nps,
                GREATEST(
                    IF(
                        DATE(s.Last_Hire_Date) < DATE(EXTRACT(YEAR FROM CURRENT_DATE()) - IF(EXTRACT(MONTH FROM CURRENT_DATE()) < 7, 1, 0), 1, 1),
                        EXTRACT(YEAR FROM CURRENT_DATE()) - EXTRACT(YEAR FROM DATE(s.Last_Hire_Date)),
                        EXTRACT(YEAR FROM CURRENT_DATE()) - EXTRACT(YEAR FROM DATE(s.Last_Hire_Date)) - 1
                    ),
                    0
                ) as years_of_service
            FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
            LEFT JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
                ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
            WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        )
        SELECT
            CASE
                WHEN years_of_service < 1 THEN '< 1 year'
                WHEN years_of_service < 3 THEN '1-2 years'
                WHEN years_of_service < 5 THEN '3-4 years'
                WHEN years_of_service < 10 THEN '5-9 years'
                ELSE '10+ years'
            END as name,
            CASE
                WHEN years_of_service < 1 THEN 1
                WHEN years_of_service < 3 THEN 2
                WHEN years_of_service < 5 THEN 3
                WHEN years_of_service < 10 THEN 4
                ELSE 5
            END as sort_order,
            COUNT(*) as total_staff,
            SUM(CASE WHEN Return IS NOT NULL THEN 1 ELSE 0 END) as responded,
            SUM(CASE WHEN Return = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN Return = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN Return = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(nps), 1) as avg_nps
        FROM staff_with_tenure
        GROUP BY name, sort_order
        ORDER BY sort_order
        """

        # By job title
        job_query = """
        SELECT
            s.Job_Title as name,
            COUNT(*) as total_staff,
            SUM(CASE WHEN i.Return IS NOT NULL THEN 1 ELSE 0 END) as responded,
            SUM(CASE WHEN i.Return = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN i.Return = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN i.Return = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS)), 1) as avg_nps
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        LEFT JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        GROUP BY s.Job_Title
        ORDER BY total_staff DESC
        """

        def process_overall(row):
            nps_total = row.nps_respondents or 0
            nps_score = 0
            if nps_total > 0:
                nps_score = round(((row.promoters or 0) - (row.detractors or 0)) / nps_total * 100, 1)
            return {
                'total_staff': row.total_staff,
                'responded': row.responded,
                'response_rate': round((row.responded / row.total_staff) * 100, 1) if row.total_staff else 0,
                'returning_yes': row.returning_yes,
                'returning_no': row.returning_no,
                'unsure': row.unsure,
                'return_rate': round((row.returning_yes / row.responded) * 100, 1) if row.responded else 0,
                'avg_nps': row.avg_nps or 0,
                'nps_score': nps_score,
                'promoters': row.promoters or 0,
                'passives': row.passives or 0,
                'detractors': row.detractors or 0,
                'nps_respondents': nps_total
            }

        def process_breakdown(rows):
            return [
                {
                    'name': r.name,
                    'total_staff': r.total_staff,
                    'responded': r.responded,
                    'response_rate': round((r.responded / r.total_staff) * 100, 1) if r.total_staff else 0,
                    'returning_yes': r.returning_yes,
                    'returning_no': r.returning_no,
                    'unsure': r.unsure,
                    'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded else 0,
                    'avg_nps': r.avg_nps or 0
                }
                for r in rows
            ]

        overall = list(client.query(overall_query).result())[0]
        locations = list(client.query(location_query).result())
        roles = list(client.query(role_query).result())
        tenures = list(client.query(tenure_query).result())
        jobs = list(client.query(job_query).result())

        return jsonify({
            'year': '2025-26',
            'overall': process_overall(overall),
            'by_location': process_breakdown(locations),
            'by_role': process_breakdown(roles),
            'by_tenure': process_breakdown(tenures),
            'by_job': process_breakdown(jobs)
        })

    except Exception as e:
        logger.error(f"Error fetching current year data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/last-year')
@login_required
def get_last_year():
    """Get last year (2024-25) ITR data."""
    if not client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Overall summary
        overall_query = """
        SELECT
            COUNT(*) as responded,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_), 1) as avg_nps,
            SUM(CASE WHEN On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_ >= 9 THEN 1 ELSE 0 END) as promoters,
            SUM(CASE WHEN On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_ BETWEEN 7 AND 8 THEN 1 ELSE 0 END) as passives,
            SUM(CASE WHEN On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_ <= 6 AND On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_ IS NOT NULL THEN 1 ELSE 0 END) as detractors,
            SUM(CASE WHEN On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_ IS NOT NULL THEN 1 ELSE 0 END) as nps_respondents
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        """

        # By site
        location_query = """
        SELECT
            Site as name,
            COUNT(*) as responded,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_), 1) as avg_nps
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        GROUP BY Site
        ORDER BY Site
        """

        # By role
        role_query = """
        SELECT
            Job_Function as name,
            COUNT(*) as responded,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_), 1) as avg_nps
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        GROUP BY Job_Function
        ORDER BY Job_Function
        """

        # By job title
        job_query = """
        SELECT
            Job_Title as name,
            COUNT(*) as responded,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Yes' THEN 1 ELSE 0 END) as returning_yes,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'No' THEN 1 ELSE 0 END) as returning_no,
            SUM(CASE WHEN Do_you_plan_to_return_to_FirstLine_for_the_2025_26_school_year_ = 'Unsure' THEN 1 ELSE 0 END) as unsure,
            ROUND(AVG(On_a_scale_of_1_10__how_would_you_recommend_working_at_FirstLine_to_a_friend_), 1) as avg_nps
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        GROUP BY Job_Title
        ORDER BY responded DESC
        """

        def process_overall(row):
            nps_total = row.nps_respondents or 0
            nps_score = 0
            if nps_total > 0:
                nps_score = round(((row.promoters or 0) - (row.detractors or 0)) / nps_total * 100, 1)
            return {
                'responded': row.responded,
                'returning_yes': row.returning_yes,
                'returning_no': row.returning_no,
                'unsure': row.unsure,
                'return_rate': round((row.returning_yes / row.responded) * 100, 1) if row.responded else 0,
                'avg_nps': row.avg_nps or 0,
                'nps_score': nps_score,
                'promoters': row.promoters or 0,
                'passives': row.passives or 0,
                'detractors': row.detractors or 0,
                'nps_respondents': nps_total
            }

        def process_breakdown(rows):
            return [
                {
                    'name': r.name,
                    'responded': r.responded,
                    'returning_yes': r.returning_yes,
                    'returning_no': r.returning_no,
                    'unsure': r.unsure,
                    'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded else 0,
                    'avg_nps': r.avg_nps or 0
                }
                for r in rows
            ]

        overall = list(client.query(overall_query).result())[0]
        locations = list(client.query(location_query).result())
        roles = list(client.query(role_query).result())
        jobs = list(client.query(job_query).result())

        return jsonify({
            'year': '2024-25',
            'overall': process_overall(overall),
            'by_location': process_breakdown(locations),
            'by_role': process_breakdown(roles),
            'by_job': process_breakdown(jobs),
            'site_mapping': SITE_MAPPING,
            'function_mapping': FUNCTION_MAPPING
        })

    except Exception as e:
        logger.error(f"Error fetching last year data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/analysis')
@login_required
def get_analysis():
    """Get detailed analysis comparing both years."""
    if not client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Non-respondents this year
        non_respondents_query = """
        SELECT
            s.Location_Name as location,
            s.Job_Function as role,
            s.Job_Title as job_title,
            COUNT(*) as count
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        LEFT JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        AND i.Return IS NULL
        GROUP BY s.Location_Name, s.Job_Function, s.Job_Title
        ORDER BY count DESC
        LIMIT 20
        """

        # Unsure respondents breakdown
        unsure_query = """
        SELECT
            s.Location_Name as location,
            s.Job_Function as role,
            COUNT(*) as count
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        AND i.Return = 'Unsure'
        GROUP BY s.Location_Name, s.Job_Function
        ORDER BY count DESC
        """

        # Not returning breakdown
        not_returning_query = """
        SELECT
            s.Location_Name as location,
            s.Job_Function as role,
            s.Job_Title as job_title
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        AND i.Return = 'No'
        """

        # Detractors (NPS 0-6)
        detractors_query = """
        SELECT
            s.Location_Name as location,
            s.Job_Function as role,
            COUNT(*) as count,
            ROUND(AVG(COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS)), 1) as avg_score
        FROM `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` s
        JOIN `talent-demo-482004.intent_to_return.intent_to_return_native` i
            ON LOWER(s.Email_Address) = LOWER(i.Email_Address)
        WHERE s.Employment_Status IN ('Active', 'Leave of absence')
        AND COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) <= 6
        GROUP BY s.Location_Name, s.Job_Function
        ORDER BY count DESC
        """

        non_respondents = [
            {'location': r.location, 'role': r.role, 'job_title': r.job_title, 'count': r.count}
            for r in client.query(non_respondents_query).result()
        ]

        unsure = [
            {'location': r.location, 'role': r.role, 'count': r.count}
            for r in client.query(unsure_query).result()
        ]

        not_returning = [
            {'location': r.location, 'role': r.role, 'job_title': r.job_title}
            for r in client.query(not_returning_query).result()
        ]

        detractors = [
            {'location': r.location, 'role': r.role, 'count': r.count, 'avg_score': r.avg_score}
            for r in client.query(detractors_query).result()
        ]

        return jsonify({
            'non_respondents': non_respondents,
            'unsure': unsure,
            'not_returning': not_returning,
            'detractors': detractors
        })

    except Exception as e:
        logger.error(f"Error fetching analysis data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/key-factors')
@login_required
def get_key_factors():
    """Get decision factors and open-ended response analysis."""
    if not client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        # Decision factors - current year (why staying)
        decision_factors_query = """
        SELECT Yes_Decision_Factors as factor, COUNT(*) as count
        FROM `talent-demo-482004.intent_to_return.intent_to_return_native`
        WHERE Yes_Decision_Factors IS NOT NULL
        AND Yes_Decision_Factors NOT IN ('N/A', 'n/a', 'NA', 'None of the above', 'All of the above')
        AND LENGTH(Yes_Decision_Factors) < 50
        GROUP BY factor
        ORDER BY count DESC
        """

        # Decision factors - last year (coded)
        decision_factors_ly_query = """
        SELECT
            CASE
                WHEN LOWER(Most_important_factor_coded) = 'firstline\\'s mission' THEN 'FirstLine\\'s mission'
                WHEN LOWER(Most_important_factor_coded) = 'school leadership' THEN 'School leadership'
                WHEN LOWER(Most_important_factor_coded) = 'compensation & benefits' THEN 'Compensation & benefits'
                WHEN LOWER(Most_important_factor_coded) = 'network leadership' THEN 'Network leadership'
                WHEN LOWER(Most_important_factor_coded) = 'hours & workload' THEN 'Hours & workload'
                ELSE Most_important_factor_coded
            END as factor,
            COUNT(*) as count
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        WHERE Most_important_factor_coded IS NOT NULL
        GROUP BY factor
        ORDER BY count DESC
        """

        # Top factors for recommending - current year
        recommend_factors_query = """
        SELECT Yes_Top_Factors_Recommend_FLS as factor, COUNT(*) as count
        FROM `talent-demo-482004.intent_to_return.intent_to_return_native`
        WHERE Yes_Top_Factors_Recommend_FLS IS NOT NULL
        GROUP BY factor
        ORDER BY count DESC
        """

        # Top factors for recommending - last year
        recommend_factors_ly_query = """
        SELECT What_is_the_top_factor_for_why_you_would_recommend_working_at_FirstLine_ as factor, COUNT(*) as count
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        WHERE What_is_the_top_factor_for_why_you_would_recommend_working_at_FirstLine_ IS NOT NULL
        GROUP BY factor
        ORDER BY count DESC
        """

        # Open-ended: Retention improvement (current year)
        retention_quotes_query = """
        SELECT
            COALESCE(Yes_Improve_Retention_Open, Maybe_Improve_Retention_Open, No_Improve_Retention_Open) as quote,
            CASE
                WHEN Yes_Improve_Retention_Open IS NOT NULL THEN 'Yes'
                WHEN Maybe_Improve_Retention_Open IS NOT NULL THEN 'Unsure'
                ELSE 'No'
            END as return_status
        FROM `talent-demo-482004.intent_to_return.intent_to_return_native`
        WHERE COALESCE(Yes_Improve_Retention_Open, Maybe_Improve_Retention_Open, No_Improve_Retention_Open) IS NOT NULL
        AND LENGTH(COALESCE(Yes_Improve_Retention_Open, Maybe_Improve_Retention_Open, No_Improve_Retention_Open)) > 30
        ORDER BY LENGTH(COALESCE(Yes_Improve_Retention_Open, Maybe_Improve_Retention_Open, No_Improve_Retention_Open)) DESC
        LIMIT 50
        """

        # Open-ended: Adult culture (current year)
        culture_quotes_query = """
        SELECT
            COALESCE(Yes_Adult_Culture_Open, Maybe_Adult_Culture_Open, No_Adult_Culture_Open) as quote,
            CASE
                WHEN Yes_Adult_Culture_Open IS NOT NULL THEN 'Yes'
                WHEN Maybe_Adult_Culture_Open IS NOT NULL THEN 'Unsure'
                ELSE 'No'
            END as return_status
        FROM `talent-demo-482004.intent_to_return.intent_to_return_native`
        WHERE COALESCE(Yes_Adult_Culture_Open, Maybe_Adult_Culture_Open, No_Adult_Culture_Open) IS NOT NULL
        AND LENGTH(COALESCE(Yes_Adult_Culture_Open, Maybe_Adult_Culture_Open, No_Adult_Culture_Open)) > 30
        ORDER BY LENGTH(COALESCE(Yes_Adult_Culture_Open, Maybe_Adult_Culture_Open, No_Adult_Culture_Open)) DESC
        LIMIT 50
        """

        # Open-ended: Retention improvement (last year)
        retention_quotes_ly_query = """
        SELECT What_could_FirstLine_do_to_improve_staff_retention_in_the_future_ as quote
        FROM `talent-demo-482004.intent_to_return.intent_to_return_25_native`
        WHERE What_could_FirstLine_do_to_improve_staff_retention_in_the_future_ IS NOT NULL
        AND LENGTH(What_could_FirstLine_do_to_improve_staff_retention_in_the_future_) > 30
        ORDER BY LENGTH(What_could_FirstLine_do_to_improve_staff_retention_in_the_future_) DESC
        LIMIT 30
        """

        decision_factors = [
            {'factor': r.factor, 'count': r.count}
            for r in client.query(decision_factors_query).result()
        ]

        decision_factors_ly = [
            {'factor': r.factor, 'count': r.count}
            for r in client.query(decision_factors_ly_query).result()
        ]

        recommend_factors = [
            {'factor': r.factor, 'count': r.count}
            for r in client.query(recommend_factors_query).result()
        ]

        recommend_factors_ly = [
            {'factor': r.factor, 'count': r.count}
            for r in client.query(recommend_factors_ly_query).result()
        ]

        retention_quotes = [
            {'quote': r.quote, 'return_status': r.return_status}
            for r in client.query(retention_quotes_query).result()
        ]

        culture_quotes = [
            {'quote': r.quote, 'return_status': r.return_status}
            for r in client.query(culture_quotes_query).result()
        ]

        retention_quotes_ly = [
            {'quote': r.quote}
            for r in client.query(retention_quotes_ly_query).result()
        ]

        return jsonify({
            'decision_factors': {
                'current': decision_factors,
                'last_year': decision_factors_ly
            },
            'recommend_factors': {
                'current': recommend_factors,
                'last_year': recommend_factors_ly
            },
            'open_ended': {
                'retention': retention_quotes,
                'culture': culture_quotes,
                'retention_last_year': retention_quotes_ly
            }
        })

    except Exception as e:
        logger.error(f"Error fetching key factors data: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
