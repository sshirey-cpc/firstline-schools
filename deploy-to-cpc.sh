#!/bin/bash
# Deployment script for Confluence Point Consulting GCP
# Usage: ./deploy-to-cpc.sh <service-name> <source-directory>

set -e

SERVICE_NAME=${1:-"my-service"}
SOURCE_DIR=${2:-.}
PROJECT="confluence-point-consulting"
REGION="us-central1"
SERVICE_ACCOUNT="cloudrun-apps@confluence-point-consulting.iam.gserviceaccount.com"

echo "Deploying $SERVICE_NAME to Confluence Point Consulting GCP..."

gcloud run deploy "$SERVICE_NAME" \
  --source "$SOURCE_DIR" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --project "$PROJECT" \
  --service-account "$SERVICE_ACCOUNT" \
  --set-env-vars "BIGQUERY_PROJECT=$PROJECT"

echo "✅ Deployment complete!"
echo "URL: https://$SERVICE_NAME-824445909534.$REGION.run.app"
