"""Run the deterministic convert, classify, extract, and comparison stages."""
from __future__ import annotations

import argparse
import time

from ..classify.pipeline import classify_all
from ..compare import compare_all
from ..config import settings_from_env
from ..db import database
from ..extract.pipeline import extract_all
from .convert import convert_all
from .ingest import ingest


def _record_stage(settings, stage: str, duration_ms: int, *, conversion: bool = False) -> None:
    """Persist a compact per-email stage outcome for the Runs/retry surface."""
    with database(settings.database_path) as connection:
        rows = connection.execute(
            """SELECT e.email_id,
                      MAX(CASE WHEN d.convert_status = 'failed' THEN 1 ELSE 0 END) AS has_failed_document
               FROM emails e LEFT JOIN documents d ON d.email_id = e.email_id
               GROUP BY e.email_id"""
        ).fetchall()
        for row in rows:
            failed = conversion and bool(row["has_failed_document"])
            connection.execute(
                """INSERT INTO stage_runs (email_id, stage, state, error, duration_ms)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(email_id, stage) DO UPDATE SET
                     state=excluded.state, error=excluded.error, duration_ms=excluded.duration_ms,
                     updated_at=CURRENT_TIMESTAMP""",
                (row["email_id"], stage, "failed" if failed else "ok", "document_conversion_failed" if failed else None, duration_ms),
            )


def _run_stage(settings, stage: str, operation, *, conversion: bool = False):
    started = time.perf_counter()
    result = operation()
    _record_stage(settings, stage, round((time.perf_counter() - started) * 1000), conversion=conversion)
    return result


def run_all():
    settings = settings_from_env()
    ingest(settings)
    _run_stage(settings, "convert", lambda: convert_all(settings), conversion=True)
    _run_stage(settings, "classify", lambda: classify_all(settings))
    _run_stage(settings, "extract", lambda: extract_all(settings))
    return _run_stage(settings, "compare", lambda: compare_all(settings))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run every pipeline stage")
    parser.parse_args()
    results = run_all()
    counts = {status: sum(item["status"] == status for item in results) for status in ("OK", "MISMATCH", "NEEDS_REVIEW")}
    print(counts)


if __name__ == "__main__":
    main()
