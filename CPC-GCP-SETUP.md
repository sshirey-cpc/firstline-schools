# Confluence Point Consulting GCP Configuration

## Project Details
- **Project ID**: confluence-point-consulting
- **Project Number**: 824445909534
- **Region**: us-central1

## Configured Settings

### 1. Organization Policy (Public Access)
✅ Project-level policy allows all domains for IAM bindings
- This means Cloud Run services can be made public without restrictions

### 2. Service Account for Cloud Run Apps
✅ Created: `cloudrun-apps@confluence-point-consulting.iam.gserviceaccount.com`
- **Permissions**:
  - `roles/bigquery.dataViewer` - Read BigQuery data
  - `roles/bigquery.jobUser` - Run BigQuery queries

### 3. Cloud Build Permissions
✅ Default compute service account has:
- `roles/storage.admin` - Upload build artifacts
- `roles/artifactregistry.writer` - Push Docker images
- `roles/logging.logWriter` - Write build logs

## Deploying New Services

### Quick Deploy
Use the deployment script:
```bash
cd /Users/scottshirey/firstline-schools
./deploy-to-cpc.sh <service-name> <source-directory>
```

Example:
```bash
./deploy-to-cpc.sh my-dashboard ./dashboards/my-dashboard
```

### Manual Deploy
```bash
gcloud run deploy <service-name> \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --project confluence-point-consulting \
  --service-account cloudrun-apps@confluence-point-consulting.iam.gserviceaccount.com \
  --set-env-vars "BIGQUERY_PROJECT=confluence-point-consulting"
```

## Deployed Services

### Grow Dashboard
- **URL**: https://grow-dashboard-824445909534.us-central1.run.app
- **Status**: ✅ Live and public
- **Features**: Action steps and goals tracking from Grow platform
- **BigQuery Access**: Read-only access to `confluence-point-consulting.grow.*` tables

## Adding BigQuery Permissions
If a service needs BigQuery access, it's already configured via the `cloudrun-apps` service account.

To add additional dataset permissions:
```bash
bq add-iam-policy-binding \
  --member="serviceAccount:cloudrun-apps@confluence-point-consulting.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" \
  confluence-point-consulting:dataset_name
```

## Making Services Public
Services deployed with `--allow-unauthenticated` will be automatically public. No additional IAM configuration needed.

## Troubleshooting

### "Failed to fetch data" errors
- Check service account has BigQuery permissions
- Restart service: `gcloud run services update <service-name> --region us-central1 --project confluence-point-consulting`

### "Permission denied" on deployment
- Ensure you're authenticated: `gcloud auth login sshirey@confluencepointconsulting.com`
- Check project: `gcloud config get-value project` should show `confluence-point-consulting`
