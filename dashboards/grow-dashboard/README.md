# Teacher Action Steps Dashboard

A Next.js dashboard for tracking teacher action steps from the Grow API, styled with FirstLine Schools branding.

## Features

- **By Location View**: See action steps statistics grouped by school location
- **By Coach View**: See action steps statistics grouped by coach within each location
- **Trimester Breakdown**:
  - Trimester 1: Through November 5th, 2025
  - Trimester 2: November 6th through current date
- **Real-time Data**: Connects directly to BigQuery for live data
- **Auto-refresh**: Manual refresh button to get latest data
- **FirstLine Schools Branding**: Uses official colors, fonts, and design patterns

## Data Metrics

For each location/coach and trimester, the dashboard shows:
- Total number of active Lead Teachers
- Number and percentage of teachers with 4+ action steps
- Number and percentage of teachers with 2+ action steps
- Number and percentage of teachers with 1+ action steps

## Setup

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment variables:**

   Copy `.env.local.example` to `.env.local`:
   ```bash
   cp .env.local.example .env.local
   ```

   Update `.env.local` with your BigQuery credentials:
   ```
   BIGQUERY_PROJECT=confluence-point-consulting
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```

3. **Run the development server:**
   ```bash
   npm run dev
   ```

4. **Open the dashboard:**

   Navigate to [http://localhost:3000](http://localhost:3000)

## Project Structure

```
grow-dashboard/
├── app/
│   ├── api/data/          # API route for BigQuery data
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Main dashboard page
│   └── globals.css        # Global styles
├── components/
│   ├── Header.tsx         # Dashboard header
│   └── ActionStepsTable.tsx # Data table component
├── lib/
│   └── bigquery.ts        # BigQuery client and queries
└── public/                # Static assets
```

## Technology Stack

- **Next.js 15**: React framework with App Router
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first styling with FLS brand colors
- **Google Cloud BigQuery**: Data source
- **Open Sans**: Typography (matching supervisor dashboard)

## Data Requirements

The dashboard expects the following BigQuery tables:
- `confluence-point-consulting.grow.users` - User data including Lead Teachers
- `confluence-point-consulting.grow.assignments` - Action steps data

Filters applied:
- User type: "Lead Teacher"
- Active employees only (inactive = false or null, archived_at = null)
- Assignment type: "actionStep"

## Building for Production

```bash
npm run build
npm start
```

## Notes

- Data updates automatically when the Grow pipeline runs
- The dashboard requires valid Google Cloud credentials with BigQuery access
- Location is determined by the `default_school_id` field in the users table
