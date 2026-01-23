#!/usr/bin/env python3
"""
Intent to Return Dashboard Generator
Queries BigQuery and generates a static HTML dashboard with embedded data.
Run this script to refresh the dashboard with latest ITR data.
"""

from google.cloud import bigquery
import json
from datetime import datetime

PROJECT_ID = "talent-demo-482004"

def get_itr_data():
    """Query BigQuery and return all ITR dashboard data."""
    client = bigquery.Client(project=PROJECT_ID)

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
        SUM(CASE WHEN COALESCE(i.Yes_NPS, i.Maybe_NPS, i.No_NPS) <= 6 THEN 1 ELSE 0 END) as detractors
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

    # By role/function
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

    # By tenure
    tenure_query = """
    SELECT
        CASE
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 1 THEN '< 1 year'
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 3 THEN '1-2 years'
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 5 THEN '3-4 years'
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 10 THEN '5-9 years'
            ELSE '10+ years'
        END as name,
        CASE
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 1 THEN 1
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 3 THEN 2
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 5 THEN 3
            WHEN DATE_DIFF(CURRENT_DATE(), DATE(s.Last_Hire_Date), YEAR) < 10 THEN 4
            ELSE 5
        END as sort_order,
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
    GROUP BY name, sort_order
    ORDER BY sort_order
    """

    # By job title (top 20)
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

    # Combined location + role breakdown
    location_role_query = """
    SELECT
        s.Location_Name as location,
        s.Job_Function as role,
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
    GROUP BY s.Location_Name, s.Job_Function
    ORDER BY s.Location_Name, s.Job_Function
    """

    def run_query(query):
        return list(client.query(query).result())

    overall = run_query(overall_query)[0]
    locations = run_query(location_query)
    roles = run_query(role_query)
    tenures = run_query(tenure_query)
    jobs = run_query(job_query)
    location_roles = run_query(location_role_query)

    # Calculate NPS score
    nps_respondents = overall.promoters + overall.passives + overall.detractors
    nps_score = 0
    if nps_respondents > 0:
        nps_score = round(((overall.promoters - overall.detractors) / nps_respondents) * 100)

    return {
        'generated_at': datetime.now().isoformat(),
        'overall': {
            'total_staff': overall.total_staff,
            'responded': overall.responded,
            'response_rate': round((overall.responded / overall.total_staff) * 100, 1) if overall.total_staff > 0 else 0,
            'returning_yes': overall.returning_yes,
            'returning_no': overall.returning_no,
            'unsure': overall.unsure,
            'return_rate': round((overall.returning_yes / overall.responded) * 100, 1) if overall.responded > 0 else 0,
            'avg_nps': overall.avg_nps or 0,
            'nps_score': nps_score,
            'promoters': overall.promoters,
            'passives': overall.passives,
            'detractors': overall.detractors
        },
        'by_location': [
            {
                'name': r.name,
                'total_staff': r.total_staff,
                'responded': r.responded,
                'response_rate': round((r.responded / r.total_staff) * 100, 1) if r.total_staff > 0 else 0,
                'returning_yes': r.returning_yes,
                'returning_no': r.returning_no,
                'unsure': r.unsure,
                'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded > 0 else 0,
                'avg_nps': r.avg_nps or 0
            }
            for r in locations
        ],
        'by_role': [
            {
                'name': r.name,
                'total_staff': r.total_staff,
                'responded': r.responded,
                'response_rate': round((r.responded / r.total_staff) * 100, 1) if r.total_staff > 0 else 0,
                'returning_yes': r.returning_yes,
                'returning_no': r.returning_no,
                'unsure': r.unsure,
                'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded > 0 else 0,
                'avg_nps': r.avg_nps or 0
            }
            for r in roles
        ],
        'by_tenure': [
            {
                'name': r.name,
                'total_staff': r.total_staff,
                'responded': r.responded,
                'response_rate': round((r.responded / r.total_staff) * 100, 1) if r.total_staff > 0 else 0,
                'returning_yes': r.returning_yes,
                'returning_no': r.returning_no,
                'unsure': r.unsure,
                'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded > 0 else 0,
                'avg_nps': r.avg_nps or 0
            }
            for r in tenures
        ],
        'by_job': [
            {
                'name': r.name,
                'total_staff': r.total_staff,
                'responded': r.responded,
                'response_rate': round((r.responded / r.total_staff) * 100, 1) if r.total_staff > 0 else 0,
                'returning_yes': r.returning_yes,
                'returning_no': r.returning_no,
                'unsure': r.unsure,
                'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded > 0 else 0,
                'avg_nps': r.avg_nps or 0
            }
            for r in jobs
        ],
        'by_location_role': [
            {
                'location': r.location,
                'role': r.role,
                'total_staff': r.total_staff,
                'responded': r.responded,
                'response_rate': round((r.responded / r.total_staff) * 100, 1) if r.total_staff > 0 else 0,
                'returning_yes': r.returning_yes,
                'returning_no': r.returning_no,
                'unsure': r.unsure,
                'return_rate': round((r.returning_yes / r.responded) * 100, 1) if r.responded > 0 else 0,
                'avg_nps': r.avg_nps or 0
            }
            for r in location_roles
        ]
    }


def generate_html(data):
    """Generate the HTML dashboard with embedded data."""

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Intent to Return Dashboard | FirstLine Schools</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        'fls-navy': '#002f60',
                        'fls-blue': '#094aad',
                        'fls-orange': '#e47727',
                        'fls-orange-dark': '#c9621e',
                        'fls-orange-light': '#f5a66d',
                        'fls-gray': '#898989',
                        'fls-light': '#f8f9fa'
                    }},
                    fontFamily: {{
                        'sans': ['Open Sans', 'sans-serif']
                    }}
                }}
            }}
        }}
    </script>
    <style>
        html {{ scroll-behavior: smooth; }}
        .stat-card {{ transition: all 0.3s ease; }}
        .stat-card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 40px rgba(0,0,0,0.15); }}
        .progress-bar {{ transition: width 0.5s ease-out; }}
        .filter-btn {{ transition: all 0.2s ease; }}
        .filter-btn:hover {{ background-color: #fff4ed; border-color: #e47727; }}
        .filter-btn.active {{ background-color: #e47727; color: white; border-color: #e47727; }}
        .data-row {{ transition: all 0.2s ease; }}
        .data-row:hover {{ background-color: #f8f9fa; }}
        .fade-in {{ animation: fadeIn 0.3s ease-in; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    </style>
</head>
<body class="font-sans bg-fls-light text-gray-800">
    <!-- Navigation -->
    <nav class="fixed top-0 left-0 right-0 bg-fls-navy text-white shadow-lg z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-fls-orange rounded-lg flex items-center justify-center font-bold text-lg">FL</div>
                    <span class="font-semibold text-lg">Intent to Return Dashboard</span>
                </div>
                <div class="hidden md:flex items-center space-x-6 text-sm">
                    <a href="#overview" class="hover:text-fls-orange transition-colors">Overview</a>
                    <a href="#location" class="hover:text-fls-orange transition-colors">By Location</a>
                    <a href="#role" class="hover:text-fls-orange transition-colors">By Role</a>
                    <a href="#tenure" class="hover:text-fls-orange transition-colors">By Tenure</a>
                    <a href="#job" class="hover:text-fls-orange transition-colors">By Job</a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <section class="pt-24 pb-12 bg-fls-navy text-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="text-center mb-8">
                <div class="inline-block px-4 py-1 bg-fls-orange/20 rounded-full text-fls-orange-light text-sm font-medium mb-4">2025-2026 School Year</div>
                <h1 class="text-4xl md:text-5xl font-bold mb-4">Intent to Return Analysis</h1>
                <p class="text-xl text-gray-300">Organization-wide retention insights</p>
                <p class="text-sm text-gray-400 mt-2">Last updated: {datetime.fromisoformat(data['generated_at']).strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
        </div>
    </section>

    <!-- Overview Stats -->
    <section id="overview" class="py-12 bg-white -mt-6 rounded-t-3xl relative z-10">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-6 mb-12">
                <!-- Response Rate -->
                <div class="stat-card bg-fls-light rounded-2xl p-6 border border-gray-200">
                    <div class="text-sm font-medium text-gray-500 mb-2">Response Rate</div>
                    <div class="text-4xl font-bold text-fls-navy">{data['overall']['response_rate']}%</div>
                    <div class="text-sm text-gray-500 mt-1">{data['overall']['responded']} of {data['overall']['total_staff']} staff</div>
                </div>

                <!-- Return Rate -->
                <div class="stat-card bg-gradient-to-br from-green-50 to-green-100 rounded-2xl p-6 border border-green-200">
                    <div class="text-sm font-medium text-green-700 mb-2">Returning (Yes)</div>
                    <div class="text-4xl font-bold text-green-700">{data['overall']['return_rate']}%</div>
                    <div class="text-sm text-green-600 mt-1">{data['overall']['returning_yes']} staff</div>
                </div>

                <!-- Unsure -->
                <div class="stat-card bg-gradient-to-br from-yellow-50 to-yellow-100 rounded-2xl p-6 border border-yellow-200">
                    <div class="text-sm font-medium text-yellow-700 mb-2">Unsure</div>
                    <div class="text-4xl font-bold text-yellow-700">{data['overall']['unsure']}</div>
                    <div class="text-sm text-yellow-600 mt-1">{round((data['overall']['unsure'] / data['overall']['responded']) * 100, 1) if data['overall']['responded'] > 0 else 0}% of responses</div>
                </div>

                <!-- Not Returning -->
                <div class="stat-card bg-gradient-to-br from-red-50 to-red-100 rounded-2xl p-6 border border-red-200">
                    <div class="text-sm font-medium text-red-700 mb-2">Not Returning</div>
                    <div class="text-4xl font-bold text-red-700">{data['overall']['returning_no']}</div>
                    <div class="text-sm text-red-600 mt-1">{round((data['overall']['returning_no'] / data['overall']['responded']) * 100, 1) if data['overall']['responded'] > 0 else 0}% of responses</div>
                </div>
            </div>

            <!-- NPS Section -->
            <div class="bg-fls-navy rounded-2xl p-8 text-white mb-12">
                <div class="grid md:grid-cols-2 gap-8 items-center">
                    <div>
                        <h3 class="text-xl font-bold mb-2">Net Promoter Score (NPS)</h3>
                        <p class="text-gray-300 text-sm mb-4">Based on the question: "How likely are you to recommend FirstLine Schools as a place to work?"</p>
                        <div class="flex items-end space-x-2">
                            <span class="text-6xl font-bold text-fls-orange">{data['overall']['nps_score']}</span>
                            <span class="text-2xl text-gray-400 mb-2">/ 100</span>
                        </div>
                    </div>
                    <div class="space-y-4">
                        <div>
                            <div class="flex justify-between text-sm mb-1">
                                <span class="text-green-400">Promoters (9-10)</span>
                                <span class="font-semibold">{data['overall']['promoters']}</span>
                            </div>
                            <div class="h-3 bg-white/20 rounded-full overflow-hidden">
                                <div class="h-full bg-green-400 rounded-full progress-bar" style="width: {round((data['overall']['promoters'] / (data['overall']['promoters'] + data['overall']['passives'] + data['overall']['detractors'])) * 100) if (data['overall']['promoters'] + data['overall']['passives'] + data['overall']['detractors']) > 0 else 0}%"></div>
                            </div>
                        </div>
                        <div>
                            <div class="flex justify-between text-sm mb-1">
                                <span class="text-yellow-400">Passives (7-8)</span>
                                <span class="font-semibold">{data['overall']['passives']}</span>
                            </div>
                            <div class="h-3 bg-white/20 rounded-full overflow-hidden">
                                <div class="h-full bg-yellow-400 rounded-full progress-bar" style="width: {round((data['overall']['passives'] / (data['overall']['promoters'] + data['overall']['passives'] + data['overall']['detractors'])) * 100) if (data['overall']['promoters'] + data['overall']['passives'] + data['overall']['detractors']) > 0 else 0}%"></div>
                            </div>
                        </div>
                        <div>
                            <div class="flex justify-between text-sm mb-1">
                                <span class="text-red-400">Detractors (0-6)</span>
                                <span class="font-semibold">{data['overall']['detractors']}</span>
                            </div>
                            <div class="h-3 bg-white/20 rounded-full overflow-hidden">
                                <div class="h-full bg-red-400 rounded-full progress-bar" style="width: {round((data['overall']['detractors'] / (data['overall']['promoters'] + data['overall']['passives'] + data['overall']['detractors'])) * 100) if (data['overall']['promoters'] + data['overall']['passives'] + data['overall']['detractors']) > 0 else 0}%"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Response Breakdown Visual -->
            <div class="bg-fls-light rounded-2xl p-6 border border-gray-200">
                <h3 class="text-lg font-bold text-fls-navy mb-4">Response Breakdown</h3>
                <div class="h-8 rounded-full overflow-hidden flex">
                    <div class="bg-green-500 h-full flex items-center justify-center text-white text-sm font-medium" style="width: {data['overall']['return_rate']}%">
                        {data['overall']['return_rate']}% Yes
                    </div>
                    <div class="bg-yellow-500 h-full flex items-center justify-center text-white text-sm font-medium" style="width: {round((data['overall']['unsure'] / data['overall']['responded']) * 100, 1) if data['overall']['responded'] > 0 else 0}%">
                        {round((data['overall']['unsure'] / data['overall']['responded']) * 100, 1) if data['overall']['responded'] > 0 else 0}%
                    </div>
                    <div class="bg-red-500 h-full flex items-center justify-center text-white text-sm font-medium" style="width: {round((data['overall']['returning_no'] / data['overall']['responded']) * 100, 1) if data['overall']['responded'] > 0 else 0}%">
                    </div>
                </div>
                <div class="flex justify-center space-x-6 mt-4 text-sm">
                    <div class="flex items-center"><span class="w-3 h-3 bg-green-500 rounded-full mr-2"></span>Returning</div>
                    <div class="flex items-center"><span class="w-3 h-3 bg-yellow-500 rounded-full mr-2"></span>Unsure</div>
                    <div class="flex items-center"><span class="w-3 h-3 bg-red-500 rounded-full mr-2"></span>Not Returning</div>
                    <div class="flex items-center"><span class="w-3 h-3 bg-gray-300 rounded-full mr-2"></span>No Response</div>
                </div>
            </div>
        </div>
    </section>

    <!-- By Location -->
    <section id="location" class="py-12 bg-fls-light">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 class="text-2xl font-bold text-fls-navy mb-6">By Location</h2>
            <div class="bg-white rounded-2xl shadow-lg overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-fls-navy text-white">
                            <tr>
                                <th class="px-6 py-4 text-left font-semibold">Location</th>
                                <th class="px-4 py-4 text-center font-semibold">Staff</th>
                                <th class="px-4 py-4 text-center font-semibold">Response Rate</th>
                                <th class="px-4 py-4 text-center font-semibold">Returning</th>
                                <th class="px-4 py-4 text-center font-semibold">Unsure</th>
                                <th class="px-4 py-4 text-center font-semibold">Not Returning</th>
                                <th class="px-4 py-4 text-center font-semibold">Avg NPS</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200">
'''

    for loc in data['by_location']:
        html += f'''                            <tr class="data-row">
                                <td class="px-6 py-4 font-medium text-fls-navy">{loc['name']}</td>
                                <td class="px-4 py-4 text-center">{loc['total_staff']}</td>
                                <td class="px-4 py-4 text-center">
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {'bg-green-100 text-green-800' if loc['response_rate'] >= 90 else 'bg-yellow-100 text-yellow-800' if loc['response_rate'] >= 75 else 'bg-red-100 text-red-800'}">
                                        {loc['response_rate']}%
                                    </span>
                                </td>
                                <td class="px-4 py-4 text-center text-green-600 font-semibold">{loc['returning_yes']} ({loc['return_rate']}%)</td>
                                <td class="px-4 py-4 text-center text-yellow-600">{loc['unsure']}</td>
                                <td class="px-4 py-4 text-center text-red-600">{loc['returning_no']}</td>
                                <td class="px-4 py-4 text-center font-semibold">{loc['avg_nps']}</td>
                            </tr>
'''

    html += '''                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </section>

    <!-- By Role -->
    <section id="role" class="py-12 bg-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 class="text-2xl font-bold text-fls-navy mb-6">By Role</h2>
            <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
'''

    for role in data['by_role']:
        html += f'''                <div class="stat-card bg-fls-light rounded-2xl p-6 border border-gray-200">
                    <div class="text-lg font-bold text-fls-navy mb-4">{role['name']}</div>
                    <div class="space-y-3">
                        <div class="flex justify-between items-center">
                            <span class="text-sm text-gray-500">Total Staff</span>
                            <span class="font-semibold">{role['total_staff']}</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-sm text-gray-500">Response Rate</span>
                            <span class="font-semibold {'text-green-600' if role['response_rate'] >= 90 else 'text-yellow-600'}">{role['response_rate']}%</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-sm text-gray-500">Returning</span>
                            <span class="font-semibold text-green-600">{role['return_rate']}%</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-sm text-gray-500">Unsure</span>
                            <span class="font-semibold text-yellow-600">{role['unsure']}</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-sm text-gray-500">Not Returning</span>
                            <span class="font-semibold text-red-600">{role['returning_no']}</span>
                        </div>
                    </div>
                </div>
'''

    html += '''            </div>
        </div>
    </section>

    <!-- By Tenure -->
    <section id="tenure" class="py-12 bg-fls-light">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 class="text-2xl font-bold text-fls-navy mb-6">By Tenure</h2>
            <div class="bg-white rounded-2xl shadow-lg overflow-hidden">
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-fls-navy text-white">
                            <tr>
                                <th class="px-6 py-4 text-left font-semibold">Tenure</th>
                                <th class="px-4 py-4 text-center font-semibold">Staff</th>
                                <th class="px-4 py-4 text-center font-semibold">Response Rate</th>
                                <th class="px-4 py-4 text-center font-semibold">Returning</th>
                                <th class="px-4 py-4 text-center font-semibold">Unsure</th>
                                <th class="px-4 py-4 text-center font-semibold">Not Returning</th>
                                <th class="px-4 py-4 text-center font-semibold">Avg NPS</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200">
'''

    for tenure in data['by_tenure']:
        html += f'''                            <tr class="data-row">
                                <td class="px-6 py-4 font-medium text-fls-navy">{tenure['name']}</td>
                                <td class="px-4 py-4 text-center">{tenure['total_staff']}</td>
                                <td class="px-4 py-4 text-center">
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {'bg-green-100 text-green-800' if tenure['response_rate'] >= 90 else 'bg-yellow-100 text-yellow-800' if tenure['response_rate'] >= 75 else 'bg-red-100 text-red-800'}">
                                        {tenure['response_rate']}%
                                    </span>
                                </td>
                                <td class="px-4 py-4 text-center text-green-600 font-semibold">{tenure['returning_yes']} ({tenure['return_rate']}%)</td>
                                <td class="px-4 py-4 text-center text-yellow-600">{tenure['unsure']}</td>
                                <td class="px-4 py-4 text-center text-red-600">{tenure['returning_no']}</td>
                                <td class="px-4 py-4 text-center font-semibold">{tenure['avg_nps']}</td>
                            </tr>
'''

    html += '''                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </section>

    <!-- By Job Title -->
    <section id="job" class="py-12 bg-white">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <h2 class="text-2xl font-bold text-fls-navy mb-6">By Job Title</h2>
            <div class="bg-fls-light rounded-2xl shadow-lg overflow-hidden">
                <div class="overflow-x-auto max-h-96">
                    <table class="w-full">
                        <thead class="bg-fls-navy text-white sticky top-0">
                            <tr>
                                <th class="px-6 py-4 text-left font-semibold">Job Title</th>
                                <th class="px-4 py-4 text-center font-semibold">Staff</th>
                                <th class="px-4 py-4 text-center font-semibold">Response Rate</th>
                                <th class="px-4 py-4 text-center font-semibold">Returning</th>
                                <th class="px-4 py-4 text-center font-semibold">Unsure</th>
                                <th class="px-4 py-4 text-center font-semibold">Not Returning</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200 bg-white">
'''

    for job in data['by_job']:
        html += f'''                            <tr class="data-row">
                                <td class="px-6 py-3 font-medium text-fls-navy text-sm">{job['name']}</td>
                                <td class="px-4 py-3 text-center text-sm">{job['total_staff']}</td>
                                <td class="px-4 py-3 text-center text-sm">{job['response_rate']}%</td>
                                <td class="px-4 py-3 text-center text-green-600 text-sm">{job['returning_yes']}</td>
                                <td class="px-4 py-3 text-center text-yellow-600 text-sm">{job['unsure']}</td>
                                <td class="px-4 py-3 text-center text-red-600 text-sm">{job['returning_no']}</td>
                            </tr>
'''

    html += '''                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer class="bg-fls-navy text-white py-8">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <div class="flex items-center justify-center space-x-3 mb-4">
                <div class="w-10 h-10 bg-fls-orange rounded-lg flex items-center justify-center font-bold text-lg">FL</div>
                <span class="text-xl font-bold">FirstLine Schools</span>
            </div>
            <p class="text-gray-400 text-sm">Intent to Return Dashboard - 2025-2026 School Year</p>
            <p class="text-gray-500 text-xs mt-2">Data refreshes when dashboard is regenerated</p>
        </div>
    </footer>
</body>
</html>
'''

    return html


def main():
    print("Fetching ITR data from BigQuery...")
    data = get_itr_data()

    print("Generating HTML dashboard...")
    html = generate_html(data)

    output_path = "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Dashboard generated: {output_path}")
    print(f"Total staff: {data['overall']['total_staff']}")
    print(f"Response rate: {data['overall']['response_rate']}%")
    print(f"Return rate: {data['overall']['return_rate']}%")


if __name__ == "__main__":
    main()
