# Project: BigQuery Dashboards

## Mandatory First Actions
1. Read `.claude/LAST_SESSION.md` (auto-generated session state)
2. Read `~/firstline-projects/.context/bigquery-dashboards/context.md` (session history)
3. Greet Scott with a brief summary of where things left off

## Tech Stack
- **Backend:** Flask + gunicorn, deployed on Google Cloud Run
- **Frontend:** Vanilla JS + Tailwind CSS (CDN) + Open Sans font
- **Data:** Native BigQuery tables in `fls-data-warehouse` (hourly scheduled refresh)
- **Auth:** Google OAuth with `@firstlineschools.org` domain restriction
- **Branding:** FirstLine Schools — orange `#e47727`, navy `#002f60`, font Open Sans

## Architecture
- GCP Project: `talent-demo-482004`
- BigQuery Dataset: `talent_grow_observations` (main), plus `payroll_validation`, `intent_to_return`, etc.
- Cloud Run Services: `bigquery-dashboards`, `supervisor-dashboard`
- Region: `us-central1`

## Key Conventions

### JavaScript
- **Always use `apiFetch()`** — never raw `fetch()`. The wrapper adds `credentials: 'include'` for session cookies and handles auth redirects. Defined in each HTML dashboard file.

### Flask / Python
- Blueprints in `blueprints/` — one per dashboard (supervisor, hr, schools, kickboard, salary, etc.)
- Config in `config.py` — all title lists, BigQuery table refs, environment settings
- Auth in `auth.py` + `blueprints/auth_routes.py`
- Role-based access by job title — never hardcode emails (only exceptions: team inboxes talent@, hr@)

### Data
- Use native BigQuery tables (not external/Google Sheets-backed)
- Scheduled queries refresh tables hourly from source sheets
- Views join tables for dashboard consumption

## Access Control Quick Reference

Full details: `docs/ACCESS_PERMISSIONS.md` | Title lists: `config.py`

### C-Team (Salary Projection + Staffing Board read access)
Job title **contains** "Chief" or "Ex. Dir" (case-insensitive). Checked in `auth.py` → `get_salary_access()`. No admin bypass — strictly title-based.

### CPO — Tier 1a (full access to all 10 dashboards)
- Chief People Officer

### HR Team — Tier 1b (Supervisor, HR, Staff List, Position Control, Onboarding)
- Chief Executive Officer, Chief HR Officer, Manager HR, Manager Payroll, Manager - Benefits, Talent Operations Manager, Recruitment Manager

### Schools Team (Schools, Kickboard, Suspensions admin)
- Chief Experience Officer, K-8 Content Lead, Dir of Culture, Dir of ESYNOLA

### School Leaders (Kickboard + Suspensions school-level access)
- Principal, Assistant Principal, Dean, Head of School, Director of Culture
- Source: `config.py` → `KICKBOARD_SCHOOL_LEADER_TITLES` (lowercase)

### Schools Dashboard Roles
| Title | Scope |
|-------|-------|
| Chief Academic Officer | all_except_cteam |
| ExDir of Teach and Learn | teachers_only |
| K-8 Content Lead | teachers_only |

### Staffing Board
- **Read:** C-Team keywords + School Director, Manager HR, Manager Payroll, Manager Finance, Talent Ops Manager, Recruitment Manager
- **Write:** CPO, Chief HR Officer, Talent Ops Manager, Recruitment Manager

### Supervisor Dashboard
- Any employee with direct reports sees their team (recursive CTE traversal of org hierarchy)
- CPO + HR Team see all teams

### Email Alias
- `zach@esynola.org` → `zodonnell@firstlineschools.org`

## Schools

| Short Name | Full Name |
|------------|-----------|
| Ashe | Arthur Ashe Charter School |
| LHA | Langston Hughes Academy |
| Wheatley | Phillis Wheatley Community School |
| Green | Samuel J. Green Charter School |

## Auth Flags (returned by `/api/auth/status`)
| Flag | Grants |
|------|--------|
| `hr_dashboard_access` | HR View |
| `schools_dashboard_access` | Schools |
| `kickboard_dashboard_access` | Kickboard |
| `suspensions_dashboard_access` | Suspensions |
| `salary_dashboard_access` | Salary Projection |
| `staffing_board_access` | Staffing Board link |
| `pcf_dashboard_access` | Position Control |
| `pcf_permissions` | PCF role object (can_approve, can_edit_final, etc.) |
| `onboarding_dashboard_access` | Onboarding |
| `onboarding_permissions` | Onboarding role object |

## BigQuery Tables

### talent-demo-482004
| Dataset | Table | Used By |
|---------|-------|---------|
| talent_grow_observations | supervisor_dashboard_data | Supervisor, HR, Schools |
| talent_grow_observations | staff_master_list_with_function | Auth lookups, Schools, Kickboard, Suspensions, Salary |
| talent_grow_observations | ldg_action_steps | Action steps (LDG sync) |
| talent_grow_observations | ldg_meetings | Meetings (LDG sync) |
| Salary | salary_schedule | Salary dashboard |
| position_control_form | requests | Position Control dashboard |
| talent_grow_observations | position_control | Staffing Board |
| onboarding_form | submissions | Onboarding dashboard |

### fls-data-warehouse (shared)
| Dataset.Table | Used By |
|---------------|---------|
| kickboard.interactions | Kickboard dashboard |
| kickboard.interactions_acl | Kickboard dashboard |
| suspensions.iss_rates_25_26 | Suspensions |
| suspensions.oss_rates_25_26 | Suspensions |
| performance_matters.results_by_test | Schools (assessment fidelity) |
| performance_matters.results_raw | Schools (student drill-down) |
| class_schedules.class_schedules | Schools (teacher rosters) |
| student_rosters.student_roster | Schools (SPED matching) |
| sps.24_25_bottom_25 | Schools (B25 flagging) |

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask app factory and blueprint registration |
| `config.py` | All title lists, BigQuery table refs, environment settings |
| `auth.py` | OAuth flow, session management, all access-check functions |
| `blueprints/` | One module per dashboard |
| `index.html` | Supervisor dashboard (main landing page) |
| `hr-dashboard.html` | HR team dashboard |
| `schools-dashboard.html` | Schools dashboard with assessment fidelity |
| `salary-dashboard.html` | Salary projection with custom scenarios |
| `kickboard-dashboard.html` | Kickboard behavioral data |
| `suspensions-dashboard.html` | Suspensions ISS/OSS data |
| `staff-list-dashboard.html` | Read-only staff directory |
| `position-control-dashboard.html` | Position Control admin panel |
| `onboarding-dashboard.html` | Onboarding admin panel |
| `orgchart.html` | Visual org hierarchy |
| `docs/ACCESS_PERMISSIONS.md` | Full permissions reference (all projects) |
| `CLAUDE_CONTEXT.md` | Project history and session log |
| `NEXT_STEPS.md` | Completed work and backlog |
| `~/firstline-projects/deploy.sh` | Deployment script (not in this repo) |

## Deployment
- Deploy dashboards app: `~/firstline-projects/deploy.sh dashboards`
- Deploy supervisor app: `~/firstline-projects/deploy.sh supervisor`
- Never use `gcloud run deploy` directly — the deploy script handles env vars and Windows `\r` stripping

## Rules
- **NEVER recommend deleting tables, scheduled queries, or infrastructure without first verifying nothing depends on them** — trace the full data flow (what feeds it, what reads from it) before suggesting any deletion
- Never guess or assume — if unsure, ask Scott first
- Never hardcode email addresses for access control — use job titles and roles
- Never commit credentials (`.gitignore` blocks `.env`, `*credentials*`, `*.json`)
- All API endpoints return JSON; HTML pages are served as static files with JS fetching data
- Test locally with `FLASK_ENV=development python app.py` before deploying
- Nav dropdown is role-aware — only shows dashboards the user can access; each page omits its own self-link
