"""Phase 7 deterministic comparison of extracted SI and BL fields."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .db import database, initialize
from .extract.aliases import FIELDS


CONFIDENCE_THRESHOLD = 0.75
PORT_CODE = re.compile(r"\(([A-Z]{2}[A-Z0-9]{3})\)\s*$", re.IGNORECASE)
SEVERITY = {field: "high" for field in FIELDS}


def _row(row):
    return dict(row) if row else None


def _ports_equal(left: dict, right: dict) -> bool:
    """Compare port names plus UN/LOCODE when both documents provide one."""
    if left["normalized"] != right["normalized"]:
        return False
    left_code = PORT_CODE.search(left["raw"] or "")
    right_code = PORT_CODE.search(right["raw"] or "")
    return not (left_code and right_code and left_code.group(1).upper() != right_code.group(1).upper())


def _equal(field: str, left: dict | None, right: dict | None) -> bool:
    if not left or not right:
        return False
    return _ports_equal(left, right) if field in {"port_of_loading", "port_of_discharge"} else left["normalized"] == right["normalized"]


def _explanation(item: dict) -> str:
    label = item["field"].replace("_", " ").title()
    return f'{label} differs: SI "{item["si_raw"]}", BL "{item["bl_raw"]}"'


def compare_email(settings, email_id: str) -> dict:
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        email = _row(connection.execute("SELECT category FROM emails WHERE email_id = ?", (email_id,)).fetchone())
        documents = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE email_id = ? ORDER BY doc_id", (email_id,))]
        extraction_rows = [dict(row) for row in connection.execute("SELECT e.* FROM extractions e JOIN documents d ON d.doc_id=e.doc_id WHERE d.email_id=?", (email_id,))]
    if not email:
        raise KeyError(email_id)
    si = [doc for doc in documents if doc["role_detected"] == "SI"]
    bl = [doc for doc in documents if doc["role_detected"] == "BL"]
    reason = None
    if email["category"] != "BL_COMPARISON":
        status = "OK"
    elif len(si) != 1 or len(bl) != 1:
        status, reason = "NEEDS_REVIEW", "missing_attachment"
    elif any(doc["convert_status"] == "failed" for doc in (*si, *bl)):
        status, reason = "NEEDS_REVIEW", "unreadable"
    elif any(not any(row["doc_id"] == doc["doc_id"] for row in extraction_rows) for doc in (*si, *bl)):
        status, reason = "NEEDS_REVIEW", "wrong_doc_type"
    else:
        by_doc = {(row["doc_id"], row["field"]): row for row in extraction_rows}
        pairs = [(field, by_doc.get((si[0]["doc_id"], field)), by_doc.get((bl[0]["doc_id"], field))) for field in FIELDS]
        if any(not left or not right or left["status"] != "found" or right["status"] != "found" for _, left, right in pairs):
            status, reason = "NEEDS_REVIEW", "missing_value"
        elif any(min(left["confidence"], right["confidence"]) < CONFIDENCE_THRESHOLD for _, left, right in pairs):
            status, reason = "NEEDS_REVIEW", "unreadable"
        else:
            unequal = [field for field, left, right in pairs if not _equal(field, left, right)]
            status = "MISMATCH" if unequal else "OK"
    by_doc = {(row["doc_id"], row["field"]): row for row in extraction_rows}
    results = []
    for field in FIELDS:
        left = by_doc.get((si[0]["doc_id"], field)) if si else None
        right = by_doc.get((bl[0]["doc_id"], field)) if bl else None
        equal = _equal(field, left, right)
        kind = "equal" if equal and left["raw"] == right["raw"] else ("format_only" if equal else "value")
        results.append({"field": field, "si_raw": left and left["raw"], "bl_raw": right and right["raw"], "si_norm": left and left["normalized"], "bl_norm": right and right["normalized"], "equal": equal, "diff_kind": kind, "confidence": min(left["confidence"], right["confidence"]) if left and right else 0.0, "severity": SEVERITY[field]})
    defects = [item["field"] for item in results if not item["equal"]] if status == "MISMATCH" else []
    explanations = [_explanation(item) for item in results if item["field"] in defects] or (["No mismatch detected"] if status == "OK" else [])
    result = {"email_id": email_id, "status": status, "review_reason": reason, "has_defect": bool(defects), "defect_fields": defects, "field_results": results, "explanations": explanations}
    with database(settings.database_path) as connection:
        connection.execute(
            """INSERT INTO comparisons (email_id,status,review_reason,has_defect,defect_fields,field_results,explanations,computed_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(email_id) DO UPDATE SET
                 status=excluded.status, review_reason=excluded.review_reason, has_defect=excluded.has_defect,
                 defect_fields=excluded.defect_fields, field_results=excluded.field_results, explanations=excluded.explanations,
                 computed_at=CASE WHEN comparisons.status IS excluded.status
                   AND comparisons.review_reason IS excluded.review_reason
                   AND comparisons.has_defect IS excluded.has_defect
                   AND comparisons.defect_fields IS excluded.defect_fields
                   AND comparisons.field_results IS excluded.field_results
                   AND comparisons.explanations IS excluded.explanations
                 THEN comparisons.computed_at ELSE excluded.computed_at END""",
            (email_id, status, reason, int(bool(defects)), json.dumps(defects), json.dumps(results), json.dumps(explanations), datetime.now(timezone.utc).isoformat()),
        )
        connection.execute(
            """INSERT INTO stage_runs (email_id, stage, state, error, duration_ms)
               VALUES (?, 'compare', 'ok', NULL, 0)
               ON CONFLICT(email_id, stage) DO UPDATE SET state='ok', error=NULL, updated_at=CURRENT_TIMESTAMP""",
            (email_id,),
        )
    return result


def compare_all(settings):
    with database(settings.database_path) as connection:
        ids = [row[0] for row in connection.execute("SELECT email_id FROM emails ORDER BY email_id")]
    return [compare_email(settings, email_id) for email_id in ids]
