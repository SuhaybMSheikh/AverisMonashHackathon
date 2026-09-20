"""Reliability primitives shared by pipeline stages and the API."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .db import database


STAGES = ("convert", "classify", "extract", "compare")
STATES = ("pending", "running", "ok", "failed", "needs_review")


def record_stage(settings, email_ids: Iterable[str], stage: str, state: str, *, error: str | None = None, duration_ms: int | None = None, method: str = "rule") -> None:
    """Upsert the observable state of one stage without hiding prior errors."""
    if stage not in STAGES or state not in STATES:
        raise ValueError("invalid stage state")
    ids = list(email_ids)
    if not ids:
        return
    with database(settings.database_path) as connection:
        for email_id in ids:
            connection.execute(
                """INSERT INTO stage_runs (email_id, stage, state, error, duration_ms)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(email_id, stage) DO UPDATE SET state=excluded.state,
                     error=excluded.error, duration_ms=excluded.duration_ms,
                     updated_at=CURRENT_TIMESTAMP""",
                (email_id, stage, state, error, duration_ms),
            )
    log_stage(settings.derived_dir, email_id=None if len(ids) != 1 else ids[0], stage=stage,
              duration_ms=duration_ms, method=method, outcome=state, error=error, count=len(ids))


def log_stage(derived_dir: Path, *, email_id: str | None, stage: str, duration_ms: int | None, method: str, outcome: str, error: str | None = None, count: int | None = None) -> None:
    """Append a JSONL event suitable for a demo or post-run diagnosis."""
    path = derived_dir / "logs" / "stages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {"at": datetime.now(timezone.utc).isoformat(), "email_id": email_id,
            "stage": stage, "duration_ms": duration_ms, "method": method,
            "outcome": outcome}
    if error:
        item["error"] = error
    if count is not None:
        item["count"] = count
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(item, sort_keys=True) + "\n")


def stage_rows(settings, *, failed_only: bool = False) -> list[dict]:
    where = "WHERE s.state IN ('failed', 'needs_review')" if failed_only else ""
    with database(settings.database_path) as connection:
        return [dict(row) for row in connection.execute(
            f"""SELECT s.email_id, s.stage, s.state, s.error, s.duration_ms, s.updated_at,
                       e.from_addr, e.subject
                FROM stage_runs s JOIN emails e ON e.email_id = s.email_id {where}
                ORDER BY CASE s.state WHEN 'failed' THEN 0 ELSE 1 END, s.updated_at DESC, s.email_id, s.stage"""
        )]


def export_snapshot(settings, output_path: Path | None = None) -> Path:
    """Write a portable, JSON-only snapshot of all state used by the API."""
    output_path = output_path or settings.derived_dir / "results_snapshot.json"
    with database(settings.database_path) as connection:
        snapshot = {table: [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
                    for table in ("emails", "documents", "extractions", "extraction_extras", "comparisons", "reviews", "stage_runs", "audit_log")}
    snapshot["generated_at"] = datetime.now(timezone.utc).isoformat()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return output_path


def restore_snapshot(settings, snapshot_path: Path) -> None:
    """Load a snapshot into the configured local database; never contacts a service."""
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    required = {"emails", "documents", "extractions", "comparisons", "stage_runs"}
    if not required.issubset(snapshot) or not all(isinstance(snapshot[key], list) for key in required):
        raise ValueError("invalid results snapshot")
    from .db import initialize
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        for table in ("audit_log", "reviews", "stage_runs", "comparisons", "extraction_extras", "extractions", "documents", "emails"):
            connection.execute(f"DELETE FROM {table}")
        for table in ("emails", "documents", "extractions", "extraction_extras", "comparisons", "reviews", "stage_runs", "audit_log"):
            rows = snapshot.get(table, [])
            if not rows:
                continue
            columns = list(rows[0])
            marks = ", ".join("?" for _ in columns)
            connection.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})",
                                   [[row.get(column) for column in columns] for row in rows])
