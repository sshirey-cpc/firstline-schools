"""
Configuration constants for Position Control.
"""

import os
import secrets

# Flask session
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# CORS
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '*').split(',')

# OAuth / domain
ALLOWED_DOMAIN = 'firstlineschools.org'
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# Dev mode - bypasses OAuth for local testing
DEV_MODE = os.environ.get('FLASK_ENV') == 'development' or not GOOGLE_CLIENT_ID
DEV_USER_EMAIL = 'sshirey@firstlineschools.org'

# Staffing Board read access — by job title (looked up from BigQuery at login)
# C-Team titles use a contains-match ("Chief" or "ExDir"), same as salary dashboard
STAFFING_BOARD_C_TEAM_KEYWORDS = ['Chief', 'ExDir']
# Additional titles that get read access beyond C-Team
STAFFING_BOARD_TITLES = [
    'School Director',
    'Manager, HR',
    'Manager Payroll',
    'Manager Finance',
    'Manager - Benefits',
    'Talent Operations Manager',
    'Recruitment Manager',
]

# BigQuery configuration
PROJECT_ID = 'talent-demo-482004'
DATASET_ID = 'talent_grow_observations'
STAFF_TABLE = 'supervisor_dashboard_data'
POSITION_TABLE = 'position_control'

# Talent team titles - users with these job titles can add positions
TALENT_TITLES = [
    'Chief People Officer',
    'Chief HR Officer',
    'Talent Operations Manager',
    'Recruitment Manager',
]

# School name mapping for display
SITE_SCHOOLS = ['Arthur Ashe', 'Samuel J Green', 'Langston Hughes', 'Phillis Wheatley']
