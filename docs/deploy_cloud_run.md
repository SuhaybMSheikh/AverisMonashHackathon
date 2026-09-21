# Cloud Run demo deployment

This deployment is intentionally a snapshot-backed demo.  The image includes
the participant `data/`, the frozen results snapshot, and the canonical text
needed for document views.  It does not include `.env`, API keys, virtual
environments, Gemini caches, dev labels, or recordings.  Gemini is disabled.
`.gcloudignore` keeps the snapshot and canonical text in the Cloud Build upload
while excluding local secrets and generated caches.

## Prerequisites

Install and authenticate the Google Cloud CLI.  This project is configured as
`averismonashhackathon-509310`; the deployment region is `asia-southeast1`
(Singapore).  Run these commands from the repository root.

```bash
gcloud auth login
gcloud config set project averismonashhackathon-509310
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create averis-demo --repository-format=docker --location=asia-southeast1
gcloud builds submit --tag asia-southeast1-docker.pkg.dev/averismonashhackathon-509310/averis-demo/document-desk:demo
gcloud run deploy document-desk-demo \
  --image asia-southeast1-docker.pkg.dev/averismonashhackathon-509310/averis-demo/document-desk:demo \
  --region asia-southeast1 \
  --platform managed \
  --port 8080 \
  --set-env-vars DEMO_MODE=1,GEMINI_ENABLED=false,RESULTS_SNAPSHOT=results_snapshot.json \
  --allow-unauthenticated
```

The first three commands above were reported as completed.  Current CLI
verification shows billing is inactive and the three deployment APIs are not
currently enabled, so the repository creation, Cloud Build, and Cloud Run
deployment have not been run.  Once billing is active, publish with the
idempotent script instead of copying the remaining commands:

```powershell
.\scripts\publish_cloud_run.ps1
```

It verifies that billing is active, enables the required APIs, creates the
Docker repository only when it does not already exist, builds the image, and
deploys the snapshot-backed demo.

Cloud Run supplies `PORT`; the image defaults to `8080` only for local use.
The required demo environment is `DEMO_MODE=1`, `GEMINI_ENABLED=false`, and
`RESULTS_SNAPSHOT=results_snapshot.json`.  The image resolves that filename
inside its `backend/derived` directory.  Do not set
`GEMINI_API_KEY` for this image.

## Local container check

```bash
docker compose up --build
curl -f http://localhost:8080/api/health
curl -f http://localhost:8080/
curl -f http://localhost:8080/email/email_004
```

The health response must report `"emails": 520`.  The last command verifies a
client-side comparison route falls back to the Vite `index.html`; open it in a
browser to load the comparison view.  Stop the local demo with:

```bash
docker compose down
```

## Required before production use

- Replace the in-container SQLite snapshot with a managed database and a
  migration/backup plan.
- Move source documents, derived text, and PDF page images to private object
  storage with lifecycle rules; do not bake customer data into images.
- Run conversion and classification in an asynchronous worker/queue, rather
  than in a request-serving instance.
- Add authentication and authorization (including review/audit permissions),
  TLS/domain controls, and rate limiting before exposing operational emails.
- Obtain approval for Gemini data handling, use a managed secret for the API
  key, document provider retention/terms, and retain the rules-only fallback.
