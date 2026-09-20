"""Run the deterministic convert, classify, extract, and comparison stages."""
from __future__ import annotations

import argparse
import time

from ..classify.pipeline import classify_all
from ..compare import compare_all
from ..config import settings_from_env
from ..db import database
from ..extract.pipeline import extract_all
from ..reliability import record_stage
from .convert import convert_all
from .ingest import ingest


def _email_ids(settings) -> list[str]:
    with database(settings.database_path) as connection:
        return [row[0] for row in connection.execute("SELECT email_id FROM emails ORDER BY email_id")]


def _record_stage(settings, stage: str, duration_ms: int, *, conversion: bool = False, email_ids: list[str] | None = None) -> None:
    """Persist per-email outcomes; conversion failures remain actionable."""
    ids = email_ids or _email_ids(settings)
    with database(settings.database_path) as connection:
        failed_ids = {row[0] for row in connection.execute(
            "SELECT DISTINCT email_id FROM documents WHERE convert_status = 'failed'"
        )} if conversion else set()
        pending_llm_ids = {row[0] for row in connection.execute(
            "SELECT email_id FROM stage_runs WHERE stage = ? AND state = 'needs_review' AND error LIKE 'pending_llm:%'", (stage,)
        )}
    record_stage(settings, (email_id for email_id in ids if email_id not in failed_ids and email_id not in pending_llm_ids), stage, "ok", duration_ms=duration_ms)
    record_stage(settings, (email_id for email_id in ids if email_id in failed_ids), stage, "failed",
                 error="unreadable: document_conversion_failed", duration_ms=duration_ms, method="converter")


def _run_stage(settings, stage: str, operation, *, conversion: bool = False, email_ids: list[str] | None = None):
    ids = email_ids or _email_ids(settings)
    record_stage(settings, ids, stage, "running")
    started = time.perf_counter()
    try:
        result = operation()
    except Exception as error:
        record_stage(settings, ids, stage, "failed", error=f"{type(error).__name__}: {error}",
                     duration_ms=round((time.perf_counter() - started) * 1000))
        raise
    _record_stage(settings, stage, round((time.perf_counter() - started) * 1000), conversion=conversion, email_ids=ids)
    return result


def run_all():
    settings = settings_from_env()
    ingest(settings)
    _run_stage(settings, "convert", lambda: convert_all(settings), conversion=True)
    _run_stage(settings, "classify", lambda: classify_all(settings))
    _run_stage(settings, "extract", lambda: extract_all(settings))
    return _run_stage(settings, "compare", lambda: compare_all(settings))


def retry_email(settings, email_id: str):
    """Retry an email from its source files, including all dependent stages."""
    # Refresh hashes first: a reviewer may have restored a repaired attachment.
    ingest(settings)
    with database(settings.database_path) as connection:
        exists = connection.execute("SELECT 1 FROM emails WHERE email_id = ?", (email_id,)).fetchone()
        document_ids = {row[0] for row in connection.execute("SELECT doc_id FROM documents WHERE email_id = ?", (email_id,))}
    if exists is None:
        raise KeyError(email_id)
    _run_stage(settings, "convert", lambda: convert_all(settings, document_ids), conversion=True, email_ids=[email_id])
    _run_stage(settings, "classify", lambda: classify_all(settings, force=True), email_ids=[email_id])
    _run_stage(settings, "extract", lambda: extract_all(settings, document_ids), email_ids=[email_id])
    return _run_stage(settings, "compare", lambda: compare_all(settings), email_ids=[email_id])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run every pipeline stage")
    parser.parse_args()
    results = run_all()
    counts = {status: sum(item["status"] == status for item in results) for status in ("OK", "MISMATCH", "NEEDS_REVIEW")}
    print(counts)


if __name__ == "__main__":
    main()
