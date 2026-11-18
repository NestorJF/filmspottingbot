#!/usr/bin/env bash
# Deploy the API to Cloud Run, with Gemini on Vertex AI and the video library in a Cloud Storage bucket.
#
#   PROJECT=my-project BUCKET=my-filmspotting-library deploy/cloudrun.sh
#
# Upload videos (and .srt/.ass subtitles) with `gcloud storage cp -r ./clips gs://$BUCKET/`;
# they are indexed when an instance starts.
set -euo pipefail

PROJECT=${PROJECT:?set PROJECT to your Google Cloud project id}
BUCKET=${BUCKET:?set BUCKET to the Cloud Storage bucket that holds the videos}
REGION=${REGION:-us-central1}
SERVICE=${SERVICE:-filmspotting}
MODEL=${MODEL:-gemini-3.5-flash}
FALLBACK_MODEL=${FALLBACK_MODEL:-}
CHAT_DAILY_LIMIT=${CHAT_DAILY_LIMIT:-200}  # the API is public: cap Gemini calls per day
SA="$SERVICE-run@$PROJECT.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    aiplatform.googleapis.com storage.googleapis.com

gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 \
    || gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access

# Least privilege: the service can call Vertex AI and read the library bucket, nothing else.
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 \
    || gcloud iam service-accounts create "$SERVICE-run" --display-name="FilmSpottingBot Cloud Run"
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
    --role=roles/aiplatform.user --condition=None >/dev/null
# A just-created service account can take a minute to propagate, so retry the bucket binding.
for attempt in 1 2 3 4 5 6; do
    gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" \
        --role=roles/storage.objectViewer >/dev/null && break
    [ "$attempt" = 6 ] && exit 1
    sleep 15
done

# New projects build with the Compute Engine default service account, which lacks build permissions.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role=roles/run.builder --condition=None >/dev/null

gcloud run deploy "$SERVICE" \
    --quiet \
    --source . \
    --region "$REGION" \
    --service-account "$SA" \
    --execution-environment gen2 \
    --add-volume "name=library,type=cloud-storage,bucket=$BUCKET,readonly=true" \
    --add-volume-mount "volume=library,mount-path=/library" \
    --set-env-vars "FILMSPOTTING_PROVIDER=google,FILMSPOTTING_GOOGLE_VERTEXAI=true,FILMSPOTTING_GOOGLE_PROJECT=$PROJECT,FILMSPOTTING_GOOGLE_LOCATION=global,FILMSPOTTING_GOOGLE_MODEL=$MODEL,FILMSPOTTING_GOOGLE_FALLBACK_MODEL=$FALLBACK_MODEL,FILMSPOTTING_CHAT_DAILY_LIMIT=$CHAT_DAILY_LIMIT" \
    --cpu 2 --memory 2Gi --timeout 300 \
    --min-instances 0 --max-instances 1 \
    --allow-unauthenticated

echo "API docs: $(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')/docs"
