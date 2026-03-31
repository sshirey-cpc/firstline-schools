"""
Flask backend for Supervisor Dashboard
App factory + blueprint registration
"""

from flask import Flask, session, request, redirect, make_response
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
import os

import time

from config import SECRET_KEY, ALLOWED_ORIGINS, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from extensions import oauth, bq_client

# Build version — set once at startup, changes with each deployment
BUILD_VERSION = str(int(time.time()))


def serve_html(filepath):
    """Serve an HTML file with automatic cache-busting.
    Redirects to a versioned URL so browsers always get fresh content after deploys."""
    req_version = request.args.get('_v', '')
    if req_version != BUILD_VERSION:
        # Preserve any other query params
        path = request.path
        return redirect(f'{path}?_v={BUILD_VERSION}')
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    response = make_response(content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    response.headers['Cache-Control'] = 'no-store'
    return response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)

    # Fix for running behind Cloud Run proxy (ensures HTTPS redirect URIs)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # Session configuration
    app.secret_key = SECRET_KEY
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'development'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # CORS
    CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

    # OAuth
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

    # Register blueprints (no url_prefix — route paths stay identical)
    from blueprints.health import bp as health_bp
    from blueprints.auth_routes import bp as auth_bp
    from blueprints.supervisor import bp as supervisor_bp
    from blueprints.hr import bp as hr_bp
    from blueprints.schools import bp as schools_bp
    from blueprints.kickboard import bp as kickboard_bp
    from blueprints.orgchart import bp as orgchart_bp
    from blueprints.staff_list import bp as staff_list_bp
    from blueprints.suspensions import bp as suspensions_bp
    from blueprints.salary import bp as salary_bp
    from blueprints.position_control import bp as pcf_bp
    from blueprints.onboarding import bp as onboarding_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(supervisor_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(schools_bp)
    app.register_blueprint(kickboard_bp)
    app.register_blueprint(orgchart_bp)
    app.register_blueprint(staff_list_bp)
    app.register_blueprint(suspensions_bp)
    app.register_blueprint(salary_bp)
    app.register_blueprint(pcf_bp)
    app.register_blueprint(onboarding_bp)

    # Refresh job title from BigQuery on every authenticated request so
    # role/access changes take effect without re-login
    @app.before_request
    def refresh_user_role():
        if 'user' in session:
            from auth import get_user_job_title
            user = session['user']
            email = user.get('email', '')
            if email:
                fresh_title = get_user_job_title(email)
                if fresh_title != user.get('job_title', ''):
                    logger.info(f"Job title changed for {email}: "
                                f"'{user.get('job_title', '')}' -> '{fresh_title}'")
                    user['job_title'] = fresh_title
                    session['user'] = user
                    session.modified = True

    # Prevent browser caching of HTML pages so deploys take effect immediately
    @app.after_request
    def set_cache_headers(response):
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        # Include build version on API responses so stale pages can auto-reload
        if response.content_type and 'application/json' in response.content_type:
            response.headers['X-Build'] = BUILD_VERSION
        return response

    return app


# Module-level app for gunicorn: `gunicorn app:app`
app = create_app()

if __name__ == '__main__':
    if not bq_client:
        logger.warning("BigQuery client is not initialized. Please check your credentials.")
        logger.warning("Run: gcloud auth application-default login")

    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'

    logger.info(f"Starting Flask server on http://localhost:{port}")
    app.run(debug=debug_mode, port=port, host='0.0.0.0')
