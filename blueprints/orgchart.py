"""Organization chart routes."""

import os
import logging
from flask import Blueprint, jsonify
from google.cloud import bigquery

from config import PROJECT_ID, DATASET_ID
from extensions import bq_client

logger = logging.getLogger(__name__)

bp = Blueprint('orgchart', __name__)

# HTML files live at the project root (one level up from blueprints/)
HTML_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@bp.route('/orgchart')
def orgchart():
    """Serve the organization chart HTML file (Google Charts version)"""
    from app import serve_html
    return serve_html(os.path.join(HTML_DIR, 'orgchart.html'))


@bp.route('/api/orgchart', methods=['GET'])
def get_orgchart_data():
    """
    Get organization chart data - all managers/supervisors with hierarchy info.
    Returns: JSON array of managers with their reporting relationships.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            WITH
            supervisor_names AS (
                SELECT DISTINCT Supervisor_Name__Unsecured_ as supervisor_key
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
                WHERE Employment_Status IN ('Active', 'Leave of absence')
                AND Supervisor_Name__Unsecured_ IS NOT NULL
                AND Salary_or_Hourly = 'Salaried'
            ),
            c_level_names AS (
                SELECT DISTINCT
                    COALESCE(sn.supervisor_key, CONCAT(s.Last_Name, ', ', s.First_Name)) as chief_name
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` s
                LEFT JOIN supervisor_names sn
                    ON LOWER(sn.supervisor_key) LIKE CONCAT(LOWER(s.Last_Name), ', ', LOWER(s.First_Name), '%')
                WHERE s.Employment_Status IN ('Active', 'Leave of absence')
                AND s.Job_Title LIKE '%Chief%'
                AND s.Salary_or_Hourly = 'Salaried'
            ),
            all_staff AS (
                SELECT
                    CASE
                        WHEN s.Preferred_First_Name IS NOT NULL
                             AND s.Preferred_First_Name != ''
                             AND LOWER(s.Preferred_First_Name) != LOWER(s.Last_Name)
                        THEN s.Preferred_First_Name
                        ELSE s.First_Name
                    END as first_name,
                    s.Last_Name as last_name,
                    CONCAT(
                        CASE
                            WHEN s.Preferred_First_Name IS NOT NULL
                                 AND s.Preferred_First_Name != ''
                                 AND LOWER(s.Preferred_First_Name) != LOWER(s.Last_Name)
                            THEN s.Preferred_First_Name
                            ELSE s.First_Name
                        END,
                        ' ', s.Last_Name
                    ) as full_name,
                    s.Job_Title as job_title,
                    s.Dept as dept,
                    s.Employment_Status as employment_status,
                    COALESCE(s.Supervisor_Name__Unsecured_, '') as reports_to,
                    COALESCE(sn.supervisor_key, CONCAT(s.Last_Name, ', ', s.First_Name)) as name_key
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function` s
                LEFT JOIN supervisor_names sn
                    ON LOWER(sn.supervisor_key) LIKE CONCAT(LOWER(s.Last_Name), ', ', LOWER(s.First_Name), '%')
                WHERE s.Employment_Status IN ('Active', 'Leave of absence')
                AND s.Salary_or_Hourly = 'Salaried'
            ),
            report_counts AS (
                SELECT
                    Supervisor_Name__Unsecured_ as supervisor_key,
                    COUNT(*) as direct_reports
                FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
                WHERE Employment_Status IN ('Active', 'Leave of absence')
                AND Supervisor_Name__Unsecured_ IS NOT NULL
                AND Salary_or_Hourly = 'Salaried'
                GROUP BY Supervisor_Name__Unsecured_
            ),
            manager_names AS (
                SELECT DISTINCT name_key
                FROM all_staff
                WHERE job_title LIKE '%Manager%'
            ),
            director_names AS (
                SELECT DISTINCT name_key
                FROM all_staff
                WHERE job_title LIKE '%Director%' OR job_title LIKE '%Dir %' OR job_title LIKE 'Dir of%'
            ),
            managers AS (
                SELECT DISTINCT
                    s.name_key,
                    s.full_name,
                    s.first_name,
                    s.last_name,
                    s.job_title,
                    s.dept,
                    s.employment_status,
                    s.reports_to,
                    COALESCE(rc.direct_reports, 0) as direct_reports
                FROM all_staff s
                LEFT JOIN report_counts rc ON s.name_key = rc.supervisor_key
                WHERE s.name_key IN (SELECT supervisor_key FROM supervisor_names)
                   OR s.reports_to IS NULL
                   OR s.reports_to = ''
                   OR s.job_title LIKE '%Chief%'
                   OR s.job_title LIKE '%Director%'
                   OR s.job_title LIKE '%ExDir%'
                   OR s.job_title LIKE '%Manager%'
                   OR s.reports_to IN (SELECT chief_name FROM c_level_names)
                   OR s.reports_to IN (SELECT name_key FROM manager_names)
                   OR s.reports_to IN (SELECT name_key FROM director_names)
            )
            SELECT * FROM managers
            ORDER BY
                CASE WHEN job_title LIKE '%CEO%' OR job_title LIKE '%Executive%' THEN 0
                     WHEN job_title LIKE '%Chief%' THEN 1
                     WHEN job_title LIKE '%ExDir%' THEN 2
                     WHEN job_title LIKE '%Director%' THEN 3
                     WHEN job_title LIKE '%Principal%' AND job_title NOT LIKE '%Asst%' THEN 4
                     WHEN job_title LIKE '%Asst Principal%' THEN 5
                     ELSE 6 END,
                last_name
        """

        logger.info("Fetching org chart data")
        query_job = bq_client.query(query)
        results = query_job.result()

        org_data = []
        for row in results:
            org_data.append({
                'name_key': row.name_key,
                'full_name': row.full_name,
                'first_name': row.first_name,
                'last_name': row.last_name,
                'job_title': row.job_title,
                'dept': row.dept,
                'employment_status': row.employment_status,
                'reports_to': row.reports_to,
                'direct_reports': row.direct_reports
            })

        logger.info(f"Found {len(org_data)} managers for org chart")
        return jsonify(org_data)

    except Exception as e:
        logger.error(f"Error fetching org chart data: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/staff-reports/<supervisor_name>', methods=['GET'])
def get_staff_reports(supervisor_name):
    """
    Get all direct reports for a supervisor (for org chart popup).
    Returns all staff who report to this person, not just managers.
    """
    if not bq_client:
        return jsonify({'error': 'BigQuery client not initialized'}), 500

    try:
        query = f"""
            SELECT
                CASE
                    WHEN Preferred_First_Name IS NOT NULL
                         AND Preferred_First_Name != ''
                         AND LOWER(Preferred_First_Name) != LOWER(Last_Name)
                    THEN Preferred_First_Name
                    ELSE First_Name
                END as First_Name,
                Last_Name,
                CONCAT(
                    CASE
                        WHEN Preferred_First_Name IS NOT NULL
                             AND Preferred_First_Name != ''
                             AND LOWER(Preferred_First_Name) != LOWER(Last_Name)
                        THEN Preferred_First_Name
                        ELSE First_Name
                    END,
                    ' ', Last_Name
                ) as full_name,
                Job_Title,
                Employment_Status
            FROM `{PROJECT_ID}.{DATASET_ID}.staff_master_list_with_function`
            WHERE Supervisor_Name__Unsecured_ = @supervisor
            AND Employment_Status IN ('Active', 'Leave of absence')
            ORDER BY Last_Name, First_Name
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("supervisor", "STRING", supervisor_name)
            ]
        )

        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()

        staff = []
        for row in results:
            staff.append({
                'first_name': row.First_Name,
                'last_name': row.Last_Name,
                'full_name': row.full_name,
                'job_title': row.Job_Title,
                'employment_status': row.Employment_Status
            })

        return jsonify(staff)

    except Exception as e:
        logger.error(f"Error fetching staff reports for {supervisor_name}: {e}")
        return jsonify({'error': str(e)}), 500
