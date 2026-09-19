# Shipping Document Verification

The Averis × Monash Hackathon project turns a read-only shipping inbox into an explainable discrepancy report. The current repository is at **Phase 0: setup and ground rules**; it has a runnable backend, a minimal frontend server, and the participant bundle arranged for the later pipeline phases.

## Pinned toolchain

- Python **3.14.0** (managed with [uv](https://docs.astral.sh/uv/))
- Node.js **24.19.0** and npm **11.17.0**
- Flask **3.1.3**

Use the exact Python and Node versions above. `uv.lock`, `requirements.txt`, `.nvmrc`, and `frontend/package.json` record the pins.

## First run

1. Install Python 3.14.0, Node 24.19.0, npm 11.17.0, and uv.
2. Copy `.env.example` to `.env`. Do not add an API key until a later phase requires Gemini.
3. Install the locked backend environment:

   ```powershell
   uv sync --locked
   ```

4. In one terminal, start the backend:

   ```powershell
   uv run python app.py
   ```

   It listens at `http://127.0.0.1:5000`; `GET /api/health` reports the indexed email and document counts.

5. In another terminal, start the frontend placeholder:

   ```powershell
   npm --prefix frontend run dev
   ```

   It listens at `http://127.0.0.1:5173`. The dashboard itself is Phase 2 work.

If GNU Make is available, use `make backend`, `make frontend`, `make pipeline`, `make reset`, `make inspect`, or `make test`. The direct commands above are the Windows-native equivalents.

## Phase 1 data layer

The backend indexes only email metadata and attachment metadata in `backend/derived/sdoc.sqlite3`; attachment bytes remain in `data/attachments/`. The ingest step is idempotent:

```powershell
uv run python -m backend.app.pipeline.ingest
uv run python -m backend.app.pipeline.ingest --reset
uv run python scripts/inspect_dataset.py
```

From the `backend/` directory, the roadmap command is also available as `python -m app.pipeline.ingest --reset`.

The read API is available at `/api/health`, `/api/emails`, `/api/emails/{email_id}`, `/api/emails/{email_id}/documents`, and `/api/documents/{doc_id}/original`. `/api/emails` returns a JSON array (520 records by default), with `X-Total-Count`, `X-Page`, and `X-Page-Size` pagination headers. It accepts `category`, `status`, `q`, `page`, and `page_size` query parameters.

## Dataset policy

`data/` contains the participant bundle (`inbox/`, `attachments/`, and `sample_submission.json`). It is input-only: never edit, regenerate, or tune against it. Derived output belongs under `backend/derived/`, which is ignored by Git.

Never open, copy, commit, or tune against an organizer answer key (`ground_truth.json`) or data-generator scripts. If an organizer bundle exposes one, notify the organizers and interact with their server only through `POST /submit`. See [FAIR_PLAY.md](FAIR_PLAY.md) for the team policy and organizer-notice template.

## Project checks

```powershell
uv run python scripts/verify_setup.py
uv run python -m unittest discover -s backend/tests -v
npm --prefix frontend run check
```

The setup verifier checks only bundle structure and schema; it never reads answer-key material.

## Repository map

```
data/               # immutable participant inputs
backend/app/        # future API and pipeline packages
backend/tests/      # Python tests
backend/derived/    # generated data, ignored
frontend/           # frontend runtime and future source
scripts/            # project commands and verification
dev_labels/         # team-authored labels only, never organizer keys
```

## Collaboration

Use a short-lived branch named `codex/<scope>`, open a focused pull request, and obtain one reviewer approval before merging. See [CONTRIBUTING.md](CONTRIBUTING.md).
