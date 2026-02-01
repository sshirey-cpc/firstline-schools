# Grow API to BigQuery Pipeline

A Python pipeline that extracts all assignment data from the Level Data Grow API and loads it into Google BigQuery.

## Features

- **OAuth 2.0 Authentication**: Automatic bearer token retrieval using client credentials
- **Automatic Pagination**: Handles 18,000+ records with auto-detected pagination
- **Data Transformation**:
  - HTML stripping from text fields
  - Nested object flattening (creator, user, progress)
  - Tag parsing
- **Robust Error Handling**: Exponential backoff retries for transient failures
- **Structured Logging**: JSON-formatted logs for easy monitoring
- **BigQuery Integration**: Automatic table creation and batch loading

## Prerequisites

1. **Python 3.8+**
2. **Grow API Credentials**: Client ID and Secret
3. **Google Cloud Project** with BigQuery enabled
4. **BigQuery Service Account** with permissions:
   - `bigquery.dataEditor` role on the dataset
   - `bigquery.jobUser` role on the project

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
GROW_CLIENT_ID=your-client-id
GROW_CLIENT_SECRET=your-client-secret
BIGQUERY_PROJECT=confluence-point-consulting
BIGQUERY_DATASET=grow
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### 3. Set Up Service Account

Download your service account JSON key from Google Cloud Console and update the `GOOGLE_APPLICATION_CREDENTIALS` path in `.env`.

Alternatively, for local development, you can use:
```bash
gcloud auth application-default login
```

## Usage

### Run the Pipeline

From the project root:

```bash
python tools/grow_pipeline/main.py
```

Or from the pipeline directory:

```bash
cd tools/grow_pipeline
python main.py
```

### Expected Output

The pipeline will:
1. Authenticate with Grow API
2. Create BigQuery table `assignments` if it doesn't exist
3. Fetch all assignments with automatic pagination
4. Transform and clean the data
5. Load data to BigQuery in batches of 1000 records
6. Print summary statistics

Example output:
```json
{"asctime": "2026-02-01 10:30:15", "name": "main", "levelname": "INFO", "message": "Starting Grow API to BigQuery pipeline"}
{"asctime": "2026-02-01 10:30:16", "name": "auth", "levelname": "INFO", "message": "Successfully authenticated with Grow API"}
{"asctime": "2026-02-01 10:30:18", "name": "api_client", "levelname": "INFO", "message": "Fetching page 1 (total records so far: 0)"}
{"asctime": "2026-02-01 10:35:42", "name": "main", "levelname": "INFO", "message": "Pipeline summary", "total_fetched": 18234, "total_loaded": 18234, "duration_seconds": 324.5}
```

## BigQuery Schema

The pipeline creates a table with the following schema:

| Field | Type | Description |
|-------|------|-------------|
| `id` | STRING | Unique assignment identifier (required) |
| `type` | STRING | Assignment type (e.g., actionStep, observation, etc.) |
| `title` | STRING | Assignment title |
| `description` | STRING | Description with HTML stripped |
| `status` | STRING | Current status |
| `due_date` | TIMESTAMP | Due date |
| `created_at` | TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |
| `creator_id` | STRING | Creator user ID |
| `creator_name` | STRING | Creator name |
| `creator_email` | STRING | Creator email |
| `user_id` | STRING | Assigned user ID |
| `user_name` | STRING | Assigned user name |
| `user_email` | STRING | Assigned user email |
| `progress_percentage` | FLOAT | Completion percentage |
| `progress_completed_steps` | INTEGER | Completed steps count |
| `progress_total_steps` | INTEGER | Total steps count |
| `tags` | STRING (REPEATED) | Array of tags |
| `ingestion_timestamp` | TIMESTAMP | When loaded to BigQuery (required) |

## Project Structure

```
tools/grow_pipeline/
├── __init__.py
├── main.py              # Main orchestrator
├── config.py            # Configuration management
├── auth.py              # API authentication
├── api_client.py        # API interaction with pagination
├── transformers.py      # Data transformation
├── bigquery_client.py   # BigQuery operations
├── schema.py            # BigQuery schema definition
└── README.md            # This file
```

## Verification

After running the pipeline, verify the data in BigQuery:

```sql
-- Check total record count
SELECT COUNT(*)
FROM `confluence-point-consulting.grow.assignments`;

-- View recent records
SELECT *
FROM `confluence-point-consulting.grow.assignments`
ORDER BY ingestion_timestamp DESC
LIMIT 10;

-- Check for duplicates
SELECT id, COUNT(*) as count
FROM `confluence-point-consulting.grow.assignments`
GROUP BY id
HAVING COUNT(*) > 1;
```

## Error Handling

The pipeline includes robust error handling:

- **Authentication errors (401/403)**: Logs clear error with troubleshooting steps
- **API errors (5xx, 429)**: Automatic retry with exponential backoff (5 attempts)
- **Transformation errors**: Logged as warnings, pipeline continues
- **BigQuery errors**: Logged, batch is skipped, pipeline continues

## Logging

Logs are output in JSON format to stdout. Key log fields:

- `levelname`: INFO, WARNING, ERROR
- `message`: Human-readable message
- Additional context in `extra` fields

## Scheduling

To run this pipeline on a schedule:

### Option 1: Cron (Linux/Mac)
```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/firstline-schools && python tools/grow_pipeline/main.py >> /path/to/logs/grow_pipeline.log 2>&1
```

### Option 2: Cloud Scheduler + Cloud Run Jobs
Deploy as a Cloud Run Job and trigger with Cloud Scheduler.

## Troubleshooting

### Authentication Fails
- Verify `GROW_CLIENT_ID` and `GROW_CLIENT_SECRET` in `.env`
- Check if credentials are still valid with the Grow API provider

### BigQuery Permission Denied
- Ensure service account has `bigquery.dataEditor` role on dataset
- Ensure service account has `bigquery.jobUser` role on project
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct

### No Records Fetched
- Check API endpoint is correct: `https://grow-api.leveldata.com/external/assignments`
- Verify bearer token is valid by checking logs
- Confirm your account has access to assignments data

### Schema Mismatch Errors
The API response structure may differ from assumptions. If you see schema errors:
1. Check the BigQuery error logs for details
2. Adjust `schema.py` to match actual API response
3. Update `transformers.py` if field names differ

## Support

For issues or questions, check the logs for detailed error messages. Most errors include specific troubleshooting guidance.
