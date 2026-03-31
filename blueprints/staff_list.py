"""Staff List Dashboard routes — customizable staff directory."""

import os
import logging
from flask import Blueprint, jsonify, request, session
from google.cloud import bigquery

from config import PROJECT_ID
from extensions import bq_client
from auth import login_required

logger = logging.getLogger(__name__)

bp = Blueprint('staff_list', __name__)

HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAFF_LIST_TABLE = f'{PROJECT_ID}.talent_grow_observations.staff_master_list_with_function'


@bp.route('/staff-list-dashboard')
def staff_list_dashboard():
    """Serve the Staff List Dashboard HTML file."""
    from app import serve_html
    return serve_html(os.path.join(HTML_DIR, 'staff-list-dashboard.html'))


@bp.route('/api/staff-list/data', methods=['GET'])
@login_required
def get_staff_list_data():
    """
    Return all staff records from staff_master_list_with_function.
    Available to any @firstlineschools.org user.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    user_email = user.get('email', '').lower()

    if not user_email.endswith('@firstlineschools.org'):
        logger.warning(f"Staff list access denied for {user_email}")
        return jsonify({'error': 'Access denied. FirstLine Schools account required.'}), 403

    try:
        query = f"""
            SELECT
                Employee_Number,
                First_Name,
                Last_Name,
                Preferred_First_Name,
                Employee_Name__Last_Suffix__First_MI_ AS Full_Name,
                Email_Address,
                Job_Title,
                Job_Code,
                Job_Alike_Desc,
                Dept,
                Dept_Code,
                Function,
                Function_Code,
                Location_Name,
                Supervisor_Name__Unsecured_ AS Supervisor,
                Employment_Status,
                Full_Part_Time_Code,
                Salary_or_Hourly,
                Highest_Education_Level,
                Relevant_Years_of_Experience,
                Subject_Desc,
                Grade_Level_Desc,
                Science_of_Reading,
                Numeracy_Certification,
                Teacher_Certification,
                T_Shirt_Size_Desc,
                Work_Phone,
                GL_Account_Number,
                FORMAT_TIMESTAMP('%Y-%m-%d', Last_Hire_Date) AS Last_Hire_Date,
                FORMAT_TIMESTAMP('%m-%d', Date_Of_Birth) AS Date_Of_Birth,
                Termination_Date,
                Job_Function
            FROM `{STAFF_LIST_TABLE}`
            ORDER BY Location_Name, Last_Name, First_Name
        """
        query_job = bq_client.query(query)
        results = query_job.result()

        staff = []
        for row in results:
            record = dict(row.items())
            # Convert booleans to readable strings
            for bool_col in ['Science_of_Reading', 'Numeracy_Certification', 'Teacher_Certification']:
                val = record.get(bool_col)
                if val is True:
                    record[bool_col] = 'Yes'
                elif val is False:
                    record[bool_col] = 'No'
                else:
                    record[bool_col] = ''
            staff.append(record)

        logger.info(f"Staff list: returned {len(staff)} records to {user_email}")
        return jsonify(staff)

    except Exception as e:
        logger.error(f"Error fetching staff list: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/staff-list/filters', methods=['GET'])
@login_required
def get_staff_list_filters():
    """Return distinct filter values for dropdowns."""
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    user = session.get('user', {})
    if not user.get('email', '').lower().endswith('@firstlineschools.org'):
        return jsonify({'error': 'Access denied. FirstLine Schools account required.'}), 403

    try:
        query = f"""
            SELECT
                ARRAY_AGG(DISTINCT Location_Name IGNORE NULLS ORDER BY Location_Name) AS locations,
                ARRAY_AGG(DISTINCT Dept IGNORE NULLS ORDER BY Dept) AS departments,
                ARRAY_AGG(DISTINCT Job_Function IGNORE NULLS ORDER BY Job_Function) AS job_functions,
                ARRAY_AGG(DISTINCT Function IGNORE NULLS ORDER BY Function) AS functions,
                ARRAY_AGG(DISTINCT Employment_Status IGNORE NULLS ORDER BY Employment_Status) AS statuses,
                ARRAY_AGG(DISTINCT Supervisor_Name__Unsecured_ IGNORE NULLS ORDER BY Supervisor_Name__Unsecured_) AS supervisors,
                ARRAY_AGG(DISTINCT Subject_Desc IGNORE NULLS ORDER BY Subject_Desc) AS subjects,
                ARRAY_AGG(DISTINCT Grade_Level_Desc IGNORE NULLS ORDER BY Grade_Level_Desc) AS grade_levels,
                ARRAY_AGG(DISTINCT Salary_or_Hourly IGNORE NULLS ORDER BY Salary_or_Hourly) AS pay_types,
                ARRAY_AGG(DISTINCT Full_Part_Time_Code IGNORE NULLS ORDER BY Full_Part_Time_Code) AS ft_pt,
                ARRAY_AGG(DISTINCT Highest_Education_Level IGNORE NULLS ORDER BY Highest_Education_Level) AS education_levels
            FROM `{STAFF_LIST_TABLE}`
        """
        row = next(iter(bq_client.query(query).result()))
        filters = {k: list(v) if v else [] for k, v in dict(row.items()).items()}
        return jsonify(filters)

    except Exception as e:
        logger.error(f"Error fetching staff list filters: {e}")
        return jsonify({'error': str(e)}), 500
