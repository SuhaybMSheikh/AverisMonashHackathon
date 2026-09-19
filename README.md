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

## Phases 1–4: data, dashboard, attachment views, and canonical text

The backend indexes only email metadata and attachment metadata in `backend/derived/sdoc.sqlite3`; attachment bytes remain in `data/attachments/`. The ingest step is idempotent:

```powershell
uv run python -m backend.app.pipeline.ingest
uv run python -m backend.app.pipeline.ingest --reset
uv run python scripts/inspect_dataset.py
```

From the `backend/` directory, the roadmap command is also available as `python -m app.pipeline.ingest --reset`.

The Vite dashboard is now an inbox and attachment viewer. Select an attachment to open its default formatted label/value table or its original view. Text uses a raw text view; spreadsheets and Word files use safe, read-only grids; PDFs render cached PNG page images. Corrupt PDFs show a downloadable error card.

The read API is available at `/api/health`, `/api/emails`, `/api/emails/{email_id}`, `/api/emails/{email_id}/documents`, `/api/documents/{doc_id}/original`, `/api/documents/{doc_id}/preview`, and `/api/documents/{doc_id}/pages/{page}.png`. `/api/emails` returns a JSON array (520 records by default), with `X-Total-Count`, `X-Page`, and `X-Page-Size` pagination headers. It accepts `category`, `status`, `q`, `page`, and `page_size` query parameters.

Run the complete attachment-preview smoke test with `uv run --locked python scripts/verify_previews.py` (or `make previews`). It requests all 250 previews, checks the two known corrupt PDFs, and confirms scans expose a rendered page image.

Phase 4 converts source attachments into deterministic canonical text under `backend/derived/text/` and writes sidecar metadata under `backend/derived/meta/`. Run it with `uv run --locked python scripts/convert_all.py` (or `make convert`). The summary is expected to report 192 text, 22 spreadsheet, 8 Word, and 20 text-layer PDF conversions as `ok`; six scans are explicitly flagged until both OCR readers are configured, and two corrupt PDFs are `failed` with `corrupt_pdf`.

The formatted attachment view automatically uses canonical text after conversion. The scan vision reader is opt-in: set `GEMINI_ENABLED=true` and provide `GEMINI_API_KEY` only after approving the transmission of rendered scan pages to Gemini. A missing key never blocks the local pipeline.

## Phase 5: classification

Run the offline, rules-first classifier after conversion:

```powershell
uv run --locked python scripts/classify_all.py
uv run --locked python scripts/evaluate_classification.py
```

The classifier stores categories, confidence, reasons, and decision source in SQLite; reruns leave existing decisions untouched and make zero Gemini calls. The optional Gemini fallback is only considered when you deliberately pass `--gemini` **and** set both `GEMINI_ENABLED=true` and `GEMINI_API_KEY`. It sends untrusted email data only at that explicit opt-in point, uses temperature zero, validates strict JSON, and caches responses. With no organizer approval, keep it disabled and use the offline pipeline.

## Phase 6: extraction and normalization

After conversion, extract the seven comparison fields and their evidence into SQLite:

```powershell
uv run --locked python scripts/extract_all.py
```

This produces one `extractions` row per field per document (`found`, `blank`, or `missing`), preserves display-only labels in `extraction_extras`, and writes `backend/derived/extraction_coverage.json` plus `backend/derived/unknown_labels.json`. The parser preserves continuation lines; normalizers remove only comparison-irrelevant formatting. `--gemini` is an optional, explicit opt-in for unknown-label discovery and caches learned aliases locally.

## Phase 7: deterministic comparison

Run the complete persisted pipeline with:

```powershell
uv run --locked python -m backend.app.pipeline.runner --all
```

It converts, classifies, extracts, and compares every indexed email. For `BL_COMPARISON` emails, comparison checks the seven canonical fields in a fixed order and stores `OK`, `MISMATCH`, or `NEEDS_REVIEW` together with field evidence, human-readable explanations, and severity metadata. Missing attachments, unreadable documents, wrong document types, missing values, and low-confidence extraction take precedence over a mismatch. Port names are normalized for formatting while supplied UN/LOCODEs must agree when both documents include them.

Results are persisted in `comparisons` and available at `GET /api/emails/{email_id}/comparison`; the endpoint is read-only and returns the pipeline's stored result. Per-email `convert`, `classify`, `extract`, and `compare` stage outcomes are recorded in `stage_runs`. Re-running unchanged inputs preserves comparison timestamps and verdicts.

## Phase 8: BL comparison workspace

Open a `BL_COMPARISON` email in the dashboard to see its persisted verdict, seven fixed SI-versus-draft-BL rows, and field-summary chips. Only differing BL values receive a red highlight; the SI reference stays unhighlighted and is shown beneath each discrepancy. `NEEDS_REVIEW` cases use amber treatment and clear missing-document or unreadable-document placeholders.

The sidebar supports `Mismatch`, `Needs review`, and `OK` subfilters. The detail view has an aligned comparison view and a canonical document view, which shows the full converted SI and BL text while highlighting only differing BL values. Attachments remain downloadable as immutable originals.

## Dataset policy

`data/` contains the participant bundle (`inbox/`, `attachments/`, and `sample_submission.json`). It is input-only: never edit, regenerate, or tune against it. Derived output belongs under `backend/derived/`, which is ignored by Git.

Never open, copy, commit, or tune against an organizer answer key (`ground_truth.json`) or data-generator scripts. If an organizer bundle exposes one, notify the organizers and interact with their server only through `POST /submit`. See [FAIR_PLAY.md](FAIR_PLAY.md) for the team policy and organizer-notice template.

## Project checks

```powershell
uv run python scripts/verify_setup.py
uv run python -m unittest discover -s backend/tests -v
uv run --locked python scripts/convert_all.py
uv run --locked python scripts/report_conversion_quality.py
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
