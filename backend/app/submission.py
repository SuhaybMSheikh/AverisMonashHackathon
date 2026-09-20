"""Shared submission rows; category overrides always take precedence."""
from __future__ import annotations

import json
from pathlib import Path

from .db import database
from .extract.aliases import FIELDS


REVIEW_REASONS = frozenset({"wrong_doc_type", "missing_attachment", "unreadable", "missing_value"})
BASE_KEYS = frozenset({"category", "status", "review_reason", "defect_fields", "has_defect"})


def submission_rows(database_path, *, use_overrides: bool = True, include_decided_by: bool = False) -> dict[str, dict]:
    """Return every email in scorer shape without changing pipeline state."""
    with database(database_path) as connection:
        emails = connection.execute(
            f"""SELECT e.email_id, {"COALESCE(e.category_override, e.category)" if use_overrides else "e.category"} AS category,
                      e.decided_by, c.status, c.review_reason, c.has_defect, c.defect_fields
               FROM emails e LEFT JOIN comparisons c ON c.email_id = e.email_id
               ORDER BY e.email_id"""
        ).fetchall()
    result: dict[str, dict] = {}
    for email in emails:
        category = email["category"]
        row = {
            "category": category,
            "status": "OK", "review_reason": None, "defect_fields": [], "has_defect": False,
        }
        if category == "BL_COMPARISON":
            status = email["status"] or "NEEDS_REVIEW"
            defects = json.loads(email["defect_fields"] or "[]") if status == "MISMATCH" else []
            row.update({"status": status, "review_reason": (email["review_reason"] or "missing_attachment") if status == "NEEDS_REVIEW" else None,
                        "defect_fields": defects, "has_defect": status == "MISMATCH"})
        if include_decided_by:
            row["decided_by"] = email["decided_by"] if email["decided_by"] in {"rule", "llm"} else "rule"
        result[email["email_id"]] = row
    return result


def validate_submission(rows: dict[str, dict], sample_path: Path) -> None:
    """Fail closed if a submission differs from the published scorer schema."""
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    if set(rows) != set(sample):
        raise ValueError(f"submission ids differ: missing={len(set(sample) - set(rows))}, extra={len(set(rows) - set(sample))}")
    for email_id, row in rows.items():
        if set(row) not in (BASE_KEYS, BASE_KEYS | {"decided_by"}):
            raise ValueError(f"{email_id}: unknown or missing keys")
        if not isinstance(row["category"], str) or not isinstance(row["status"], str) or not isinstance(row["has_defect"], bool):
            raise ValueError(f"{email_id}: invalid scalar type")
        if not isinstance(row["defect_fields"], list) or any(field not in FIELDS for field in row["defect_fields"]):
            raise ValueError(f"{email_id}: invalid defect fields")
        if row["has_defect"] != (row["status"] == "MISMATCH"):
            raise ValueError(f"{email_id}: has_defect must match MISMATCH")
        if row["status"] != "MISMATCH" and row["defect_fields"]:
            raise ValueError(f"{email_id}: non-mismatch cannot carry defect fields")
        reason = row["review_reason"]
        if (row["status"] == "NEEDS_REVIEW" and reason not in REVIEW_REASONS) or (row["status"] != "NEEDS_REVIEW" and reason is not None):
            raise ValueError(f"{email_id}: invalid review reason")
        if "decided_by" in row and row["decided_by"] not in {"rule", "llm"}:
            raise ValueError(f"{email_id}: invalid decided_by")
