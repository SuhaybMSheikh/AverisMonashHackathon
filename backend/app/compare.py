"""Phase 7 deterministic comparison of extracted SI and BL fields."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from .db import database, initialize
from .extract.aliases import FIELDS
from .normalize import normalize


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


def _diff_segments(expected: str | None, actual: str | None) -> list[dict]:
    """Return safe BL display spans using case-folded token SequenceMatcher diffs."""
    if actual is None:
        return []
    if expected is None:
        return [{"text": actual, "changed": True}]
    # Keep whitespace and punctuation tokens so differences such as 40,326 vs
    # 41,326 retain their common `,326` suffix instead of highlighting a whole
    # number.  A second character pass sharpens changed token runs.
    left_tokens = re.findall(r"\w+|\s+|[^\w\s]", expected, re.UNICODE)
    right_tokens = re.findall(r"\w+|\s+|[^\w\s]", actual, re.UNICODE)
    matcher = SequenceMatcher(None, [token.casefold() for token in left_tokens], [token.casefold() for token in right_tokens], autojunk=False)
    opcodes = matcher.get_opcodes()
    if not any(tag == "equal" and j2 > j1 for tag, _, _, j1, j2 in opcodes):
        return [{"text": actual, "changed": True}]
    spans: list[dict] = []
    for tag, left_start, left_end, right_start, right_end in opcodes:
        if right_start == right_end:
            continue
        expected_text = "".join(left_tokens[left_start:left_end])
        actual_text = "".join(right_tokens[right_start:right_end])
        if tag == "equal":
            spans.append({"text": actual_text, "changed": False})
            continue
        if tag == "insert":
            spans.append({"text": actual_text, "changed": True})
            continue
        characters = SequenceMatcher(None, expected_text.casefold(), actual_text.casefold(), autojunk=False)
        for character_tag, _, _, start, end in characters.get_opcodes():
            if start != end:
                spans.append({"text": actual_text[start:end], "changed": character_tag != "equal"})
    merged: list[dict] = []
    for span in spans:
        if merged and merged[-1]["changed"] == span["changed"]:
            merged[-1]["text"] += span["text"]
        else:
            merged.append(span)
    return merged


def _review_side(field: str, left: dict | None, right: dict | None, si: list[dict], bl: list[dict], reason: str | None, reviews: dict[tuple[str, str], dict]) -> str | None:
    """Identify which source needs an amber marker without marking the reference blindly."""
    if reason == "missing_attachment":
        return "SI" if not si else "BL" if not bl else "BOTH"
    unreadable_roles = {role for (role, review_field), review in reviews.items() if review["disposition"] == "unreadable" and review_field == field}
    if unreadable_roles:
        return next(iter(unreadable_roles)) if len(unreadable_roles) == 1 else "BOTH"
    failed_roles = {doc["role_detected"] for doc in (*si, *bl) if doc["convert_status"] == "failed"}
    if failed_roles:
        return next(iter(failed_roles)) if len(failed_roles) == 1 else "BOTH"
    left_bad = not left or left["status"] != "found" or left["confidence"] < CONFIDENCE_THRESHOLD
    right_bad = not right or right["status"] != "found" or right["confidence"] < CONFIDENCE_THRESHOLD
    if left_bad and right_bad:
        return "BOTH"
    if left_bad:
        return "SI"
    if right_bad:
        return "BL"
    return "BOTH" if reason else None


def _latest_reviews(connection, email_id: str) -> tuple[dict[tuple[str, str], dict], list[dict]]:
    """Return the latest reviewer decision per SI/BL field and the audit trail.

    Reviews deliberately overlay read-only extraction rows; no source attachment
    or original parsed value is ever changed.
    """
    rows = [dict(row) for row in connection.execute(
        "SELECT id, doc_role, field, value, reviewer, note, disposition, created_at "
        "FROM reviews WHERE email_id = ? ORDER BY id", (email_id,)
    )]
    latest = {(row["doc_role"], row["field"]): row for row in rows}
    return latest, rows


def _overlay_extractions(rows: list[dict], documents: list[dict], reviews: dict[tuple[str, str], dict]) -> list[dict]:
    role_by_document = {document["doc_id"]: document["role_detected"] for document in documents}
    overlaid: list[dict] = []
    for row in rows:
        review = reviews.get((role_by_document.get(row["doc_id"]), row["field"]))
        if review and review["disposition"] == "confirmed":
            value = review["value"]
            overlaid.append({
                **row, "raw": value, "normalized": normalize(row["field"], value),
                "status": "found", "confidence": 1.0, "reviewed": True, "original_raw": row["raw"],
                "review_id": review["id"], "reviewer": review["reviewer"],
            })
        else:
            overlaid.append({**row, "reviewed": False, "original_raw": row["raw"]})
    return overlaid


def compare_email(settings, email_id: str) -> dict:
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        email = _row(connection.execute("SELECT category FROM emails WHERE email_id = ?", (email_id,)).fetchone())
        documents = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE email_id = ? ORDER BY doc_id", (email_id,))]
        extraction_rows = [dict(row) for row in connection.execute("SELECT e.* FROM extractions e JOIN documents d ON d.doc_id=e.doc_id WHERE d.email_id=?", (email_id,))]
        latest_reviews, review_history = _latest_reviews(connection, email_id)
    if not email:
        raise KeyError(email_id)
    extraction_rows = _overlay_extractions(extraction_rows, documents, latest_reviews)
    si = [doc for doc in documents if doc["role_detected"] == "SI"]
    bl = [doc for doc in documents if doc["role_detected"] == "BL"]
    reason = None
    forced_unreadable = any(review["disposition"] == "unreadable" for review in latest_reviews.values())
    forced_undetermined = any(review["disposition"] == "cannot_determine" for review in latest_reviews.values())
    if email["category"] != "BL_COMPARISON":
        status = "OK"
    elif forced_unreadable:
        status, reason = "NEEDS_REVIEW", "unreadable"
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
        elif forced_undetermined:
            status, reason = "NEEDS_REVIEW", "missing_value"
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
        results.append({"field": field, "si_raw": left and left["raw"], "bl_raw": right and right["raw"], "si_norm": left and left["normalized"], "bl_norm": right and right["normalized"], "equal": equal, "diff_kind": kind, "confidence": min(left["confidence"], right["confidence"]) if left and right else 0.0, "severity": SEVERITY[field], "si_reviewed": bool(left and left.get("reviewed")), "bl_reviewed": bool(right and right.get("reviewed")), "si_original_raw": left and left.get("original_raw"), "bl_original_raw": right and right.get("original_raw"), "bl_diff_segments": _diff_segments(left and left["raw"], right and right["raw"]) if not equal else [], "review_side": _review_side(field, left, right, si, bl, reason, latest_reviews) if status == "NEEDS_REVIEW" else None})
    defects = [item["field"] for item in results if not item["equal"]] if status == "MISMATCH" else []
    explanations = [_explanation(item) for item in results if item["field"] in defects] or (["No mismatch detected"] if status == "OK" else [])
    result = {"email_id": email_id, "status": status, "review_reason": reason, "has_defect": bool(defects), "defect_fields": defects, "field_results": results, "explanations": explanations, "reviews": review_history}
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
