# Position Control - User Guide

## Overview

Position Control is a web-based staffing management dashboard for FirstLine Schools. It provides real-time visibility into staffing levels, hiring progress, and position management across all schools.

**Live URL:** https://position-control-965913991496.us-central1.run.app

---

## Views

| View | Purpose |
|------|---------|
| 25-26 Overview | Current year staffing status and school breakdown |
| 26-27 Overview | Next year hiring progress and timeline |
| All Positions | Detailed position list with filtering and editing |

---

## 1. 25-26 Overview

### What You See

- **Staffing Progress Bar** - Overall percentage of positions filled
- **Summary Cards**:
  - Total Positions (excludes "Not Filling Seat" and "Overhire")
  - Currently Open positions
  - Returning for 26-27 (retention)
  - At Risk for 26-27 (possible departures)
- **Category Breakdown** - Teachers, Support, Leaders, Operations
- **School Cards** - Each school's staffing by category

### Status Definitions (25-26)

| Status | Meaning | Counts As |
|--------|---------|-----------|
| **Active** | Fully onboarded, in HRIS | Filled |
| **Filled** | Accepted offer, pending onboarding | Onboarding |
| **Open** | Vacant position | Open |
| **Finalist** | Candidate in final stages | Open |
| **Overhire** | Extra position for backfill | Excluded from total |
| **Not Filling Seat** | Position eliminated | Excluded from total |

### Hover for Details

Hover over any category card or school category box to see the breakdown:
- Active count
- Onboarding count
- Open count

---

## 2. 26-27 Overview

### Hiring Progress Timeline

The progress bar at the top shows:
- **Orange fill** - Current hiring progress
- **Monthly markers** - Target milestones for each month
- **Navy marker** - Current month's target
- **Status message** - "On track" or "X% behind target"

### Monthly Hiring Targets

| Month | Target % | Cumulative Hires |
|-------|----------|------------------|
| January | 7% | 6 |
| February | 16% | 13 |
| March | 33% | 27 |
| April | 50% | 41 |
| May | 72% | 59 |
| June | 88% | 72 |
| July | 95% | 78 |
| August | 100% | 82 |

### What You See

- **Summary Cards**: 26-27 Openings, Hired, Remaining, % to Goal
- **Category Cards**: Hiring progress by role type
- **School Cards**: Each school's hiring status

### Status Definitions (26-27)

| Status | Meaning |
|--------|---------|
| **Return** | Employee returning next year |
| **Possible Open** | May leave (unsure) |
| **Open** | Confirmed vacancy |
| **Filled** | New hire confirmed for 26-27 |
| **Seat Change** | Position moving/restructuring |

---

## 3. All Positions View

### Year Toggle

Switch between **25-26** and **26-27** to see:
- Different employee columns (current vs. next year)
- Different status columns
- Different status filter options

### Filters

| Filter | Purpose |
|--------|---------|
| School | Filter by specific school |
| Category | Filter by job category |
| Year Toggle | Switch between 25-26 and 26-27 data |
| Status Dropdown | Multi-select status filter |
| Search | Search by name, title, subject, school |
| Mismatches Only | Show only positions with HR discrepancies |
| Clear | Reset all filters |

### Mismatch Flags

Positions are compared against the HR system (staff_master_list). Flag indicators:

| Flag | Meaning |
|------|---------|
| **!** (Red) | Employee not found in HR system |
| **S** (Orange) | Status mismatch (e.g., HR shows "Leave of Absence") |
| **Su** (Yellow) | Subject mismatch |
| **T** (Blue) | Job title mismatch |
| **L** (Purple) | Location mismatch |
| **✓** (Green) | No mismatches |

### Editing Positions

1. **Click any row** to open the edit modal
2. **Available fields**:
   - School, Category, Job Title, Subject, Grade Level
   - Candidate Name (for tracking pre-hire pipeline)
   - 25-26 Employee, Email, Employee Number (EID)
   - 25-26 Status, 26-27 Status
   - 26-27 Employee
   - ITR Response
   - Notes
3. **Assign from HR** - Dropdown to select from unassigned staff (auto-fills name, email, EID)
4. **Clear Employee** - Click ✕ to mark position as vacant

### Adding New Positions

1. Click **"+ Add Position"** in the header
2. Fill in the required fields
3. Click **Save Changes**

### Deleting Positions

1. Click a position row to open edit modal
2. Click **"Delete Position"** (red button)
3. Confirm deletion

---

## 4. Unassigned Staff

### What It Is

The yellow **"X Unassigned"** badge in the header shows employees who are:
- Active in the HR system (HRIS)
- Not assigned to any position in Position Control

These are typically new hires who have been onboarded but need to be linked to their position.

### How to Use

1. Click the **Unassigned** badge to see the list
2. View: Name, EID, Location, Job Title, Email
3. Open an open position → Use the **"Assign from HR"** dropdown
4. Select the employee → Info auto-fills
5. Save

---

## Candidate Tracking

### Pipeline Status

When you have a candidate with an offer out but not yet in HRIS:

1. Open the position
2. Enter their name in the **Candidate** field (yellow box)
3. Leave employee fields empty
4. The position table will show their name in yellow with ⏳

### When They're Hired

1. They'll appear in the **Unassigned** list once in HRIS
2. Open the position
3. Use **Assign from HR** dropdown to select them
4. Their official name, email, and EID are auto-filled
5. Candidate name remains for reference (or clear it)

---

## Data & Calculations

### What Counts in Totals

| Included | Excluded |
|----------|----------|
| Active | Not Filling Seat |
| Filled (Onboarding) | Overhire |
| Open | |
| Finalist | |

### Percentage Calculations

- **% Staffed** = Active / Total × 100
- **% to Hiring Goal** = Hired / (Open + Possible Open + Filled) × 100

Note: With Overhire positions, you can exceed 100% staffed.

---

## Access Control

### Who Can Access

Any user with a `@firstlineschools.org` Google account can access Position Control.

### Admin Users

Admins have full edit access. Current admin list is configured in `config.py`.

---

## Data Source

All data is stored in Google BigQuery:

| Table | Purpose |
|-------|---------|
| `talent-demo-482004.talent_grow_observations.position_control` | Position data |
| `talent-demo-482004.talent_grow_observations.position_history` | Change audit log |
| `talent-demo-482004.talent_grow_observations.staff_master_list_with_function` | HR staff data |

---

## Troubleshooting

### Numbers Don't Add Up

- Check if positions have unusual statuses
- Overhire and "Not Filling Seat" are excluded from totals
- Hover over cards to see the full breakdown

### Can't Find an Employee

- Use the Search box in All Positions
- Check the **Unassigned** list if they're new
- Verify their email matches between Position Control and HR

### Mismatch Flags Showing

These indicate discrepancies between Position Control and the HR system:
- Review the position details
- Update to match HR data, or
- Investigate why there's a difference

### Data Not Updating

- Refresh the page
- Changes save immediately to BigQuery
- Check browser console for errors

---

## Contact

For access issues or questions, contact:
- Scott Shirey (sshirey@firstlineschools.org) - Chief People Officer
- Brittney Richardson (brichardson@firstlineschools.org) - Chief of Human Resources
