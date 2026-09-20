"""Shared submission rows; category overrides always take precedence."""
from __future__ import annotations

import json

from .db import database


def submission_rows(database_path) -> dict[str, dict]:
    """Return every email in scorer shape without changing pipeline state."""
    with database(database_path) as connection:
        emails = connection.execute(
            """SELECT e.email_id, COALESCE(e.category_override, e.category) AS category,
                      c.status, c.review_reason, c.has_defect, c.defect_fields
               FROM emails e LEFT JOIN comparisons c ON c.email_id = e.email_id
               ORDER BY e.email_id"""
        ).fetchall()
    result: dict[str, dict] = {}
    for email in emails:
        category = email["category"]
        if category != "BL_COMPARISON":
            result[email["email_id"]] = {"category": category, "status": "OK", "review_reason": None, "defect_fields": [], "has_defect": False}
            continue
        result[email["email_id"]] = {
            "category": category,
            "status": email["status"] or "NEEDS_REVIEW",
            "review_reason": email["review_reason"] or "missing_attachment",
            "defect_fields": json.loads(email["defect_fields"] or "[]"),
            "has_defect": bool(email["has_defect"]),
        }
    return result
