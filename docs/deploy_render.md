# Deploying the demo on Render

This project is configured as an offline demo.  The Docker build processes the
tracked `data/` inbox, creates `results_snapshot.json`, builds the frontend,
and renders PDF preview images.  No snapshot, model key, or local `.env` file
is required in the repository or build context.

## Create the service in the Render dashboard

1. Push this repository, including `Dockerfile`, `render.yaml`, `data/`, and
   `frontend/package-lock.json`, to a Git provider supported by Render.
2. In the [Render Dashboard](https://dashboard.render.com/), choose **New** →
   **Blueprint** and connect the repository.
3. Review the service named `averis-shipping-demo`.  The blueprint selects the
   Docker runtime and free plan, checks `/api/health`, and leaves automatic
   deploys off.
4. Create the Blueprint.  Do not add a start command: the image starts
   Gunicorn itself and listens on Render's `PORT` value.
5. When the build completes, open the service URL and verify
   `https://<service>.onrender.com/api/health` reports `"status":"healthy"`
   and `"emails":520`.

If creating a service without the Blueprint, choose **Web Service** and
**Docker** as the runtime, select the **Free** instance type, set the health
check path to `/api/health`, and set auto-deploy to **No**.  Use the same three
environment variables below.

## Required environment variables

| Variable | Value | Purpose |
| --- | --- | --- |
| `DEMO_MODE` | `1` | Restores the read-only demo snapshot at each container start. |
| `GEMINI_ENABLED` | `false` | Keeps the deployment offline and prevents model calls. |
| `RESULTS_SNAPSHOT` | `results_snapshot.json` | Selects the snapshot generated inside the image. |

Do not configure `GEMINI_API_KEY` for this demo. Render supplies `PORT`; the
container falls back to port `10000` only for local runs.

## Cold starts and persistence

On the free plan, a spun-down service needs to start a container before it can
answer. The image already contains the snapshot and PDF page images, so startup
only restores the snapshot to its ephemeral SQLite database. Expect the first
request after spin-down to wait for the normal Render cold start, not for data
processing or PDF rendering.

The filesystem is ephemeral. Human review records and category overrides made
through the UI are stored in that local SQLite database and reset whenever the
instance restarts or spins down. The original deterministic snapshot is restored
on the next start. Uploaded or locally generated runtime files should likewise
not be treated as persistent.

## Redeploying

With auto-deploy disabled, push the desired commit and then use **Manual Deploy**
→ **Deploy latest commit** from the service dashboard. Render rebuilds the
Docker image, recreates the demo snapshot and PDF cache from the tracked data,
and starts the new revision. Re-check `/api/health` after the deploy.
