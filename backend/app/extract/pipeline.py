"""Persist Phase 6 field evidence from deterministic canonical text."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from ..config import Settings
from ..db import database, initialize
from ..normalize import normalize
from .aliases import FIELDS, resolve
from .parser import LabelValue, parse


PLACEHOLDER = {"", "N/A", "NA", "-", "_", "____MT", "____ MT", "TBC", "NIL"}


@dataclass(frozen=True)
class FieldResult:
    field: str
    raw: str | None
    normalized: str | None
    source_doc: str
    line_no: int | None
    confidence: float
    status: str


def _blank(value: str) -> bool:
    compact = " ".join(value.upper().split())
    return compact in PLACEHOLDER or ("_" in compact and not any(char.isdigit() for char in compact))


def _prefer(field: str, entry: LabelValue) -> tuple[int, int]:
    label = entry.label.upper()
    # PDF layouts often include per-container rows. Total rows are authoritative.
    total = int(label.startswith("TOTAL") or "TOTAL " in label)
    containers = int(field == "container_count" and ("NO. OF CONTAINERS" in label or "TOTAL CONTAINERS" in label))
    return total + containers, -entry.line_no


def extract_text(text: str, doc_id: str, *, confidence: float = 1.0, uncertain_fields: set[str] | None = None, learned: dict[str, str] | None = None) -> tuple[list[FieldResult], list[LabelValue]]:
    """Extract all seven fields and retain every unmapped row as a display extra."""
    uncertain_fields = uncertain_fields or set()
    candidates: dict[str, list[tuple[LabelValue, float]]] = defaultdict(list)
    extras: list[LabelValue] = []
    for entry in parse(text):
        field, alias_confidence = resolve(entry.label)
        field = field or (learned or {}).get(entry.label)
        if field is None:
            extras.append(entry)
        else:
            candidates[field].append((entry, alias_confidence if alias_confidence else 0.95))

    results: list[FieldResult] = []
    for field in FIELDS:
        entries = candidates.get(field, [])
        if not entries:
            results.append(FieldResult(field, None, None, doc_id, None, 0.0, "missing"))
            continue
        entry, alias_confidence = max(entries, key=lambda item: _prefer(field, item[0]))
        raw = entry.raw
        is_blank = _blank(raw)
        value_confidence = min(confidence, alias_confidence)
        if field in uncertain_fields:
            value_confidence = min(value_confidence, 0.49)
        results.append(FieldResult(field, raw, None if is_blank else normalize(field, raw), doc_id, entry.line_no, value_confidence, "blank" if is_blank else "found"))
    return results, extras


def _document_metadata(settings: Settings, relative_path: str | None) -> dict:
    if not relative_path:
        return {}
    candidate = (settings.derived_dir / relative_path).resolve()
    try:
        candidate.relative_to((settings.derived_dir / "meta").resolve())
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _comparable(metadata: dict, text: str) -> bool:
    """Exclude documents that Phase 4 positively identified as the wrong type.

    They deliberately use SI/BL-looking filenames in the participant bundle, but
    are invoices or certificates rather than a shipping document to compare.
    """
    warnings = any(str(warning).startswith("wrong_doc_type_candidate:") for warning in metadata.get("warnings", []))
    # Some deliberately misnamed .txt samples declare their non-shipping type
    # inside the canonical text rather than producing a converter warning.
    upper_text = text.upper()
    declared_non_shipping = (
        "NOT A SHIPPING INSTRUCTION" in upper_text
        or "NOT AN SI OR BL" in upper_text
        or "PACKING LIST ONLY" in upper_text
    )
    return not warnings and not declared_non_shipping


def extract_all(settings: Settings, document_ids: set[str] | None = None, *, use_gemini: bool = False) -> list[FieldResult]:
    """Replace derived field evidence for selected documents; reruns are idempotent."""
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        documents = [dict(row) for row in connection.execute("SELECT doc_id, text_path, meta_path, convert_status FROM documents ORDER BY doc_id")]
    if document_ids is not None:
        documents = [document for document in documents if document["doc_id"] in document_ids]

    all_results: list[FieldResult] = []
    with database(settings.database_path) as connection:
        for document in documents:
            text = ""
            if document["convert_status"] != "failed" and document["text_path"]:
                candidate = (settings.derived_dir / document["text_path"]).resolve()
                try:
                    candidate.relative_to((settings.derived_dir / "text").resolve())
                    text = candidate.read_text(encoding="utf-8")
                except (OSError, ValueError):
                    text = ""
            metadata = _document_metadata(settings, document["meta_path"])
            if not _comparable(metadata, text):
                connection.execute("DELETE FROM extractions WHERE doc_id = ?", (document["doc_id"],))
                connection.execute("DELETE FROM extraction_extras WHERE doc_id = ?", (document["doc_id"],))
                continue
            learned: dict[str, str] = {}
            if text:
                from .aliases import normalize_label
                from .gemini_fallback import learned_aliases, resolve as resolve_unknown_labels
                cached = learned_aliases(settings.derived_dir)
                learned = {entry.label: cached[normalize_label(entry.label)] for entry in parse(text) if normalize_label(entry.label) in cached}
            if use_gemini and text:
                unknown_labels = [entry.label for entry in parse(text) if resolve(entry.label)[0] is None]
                learned.update(resolve_unknown_labels(unknown_labels, settings.derived_dir))
            results, extras = extract_text(text, document["doc_id"], confidence=float(metadata.get("confidence", 0.0)), uncertain_fields=set(metadata.get("uncertain_fields", [])), learned=learned)
            connection.execute("DELETE FROM extractions WHERE doc_id = ?", (document["doc_id"],))
            connection.execute("DELETE FROM extraction_extras WHERE doc_id = ?", (document["doc_id"],))
            connection.executemany(
                "INSERT INTO extractions (doc_id, field, raw, normalized, line_no, confidence, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(item.source_doc, item.field, item.raw, item.normalized, item.line_no, item.confidence, item.status) for item in results],
            )
            connection.executemany(
                "INSERT INTO extraction_extras (doc_id, label, raw, line_no) VALUES (?, ?, ?, ?)",
                [(document["doc_id"], item.label, item.raw, item.line_no) for item in extras],
            )
            all_results.extend(results)
    return all_results


def coverage_report(settings: Settings) -> dict:
    """Summarize seven-field coverage by source format plus unresolved labels."""
    with database(settings.database_path) as connection:
        rows = connection.execute(
            """SELECT d.ext, e.status, COUNT(*) AS count FROM documents d
               JOIN extractions e ON e.doc_id = d.doc_id GROUP BY d.ext, e.status ORDER BY d.ext, e.status"""
        ).fetchall()
        unknown = connection.execute(
            "SELECT label, COUNT(*) AS count FROM extraction_extras GROUP BY label ORDER BY count DESC, label"
        ).fetchall()
        readable_missing = connection.execute(
            """SELECT d.ext, COUNT(*) AS count FROM documents d JOIN extractions e ON e.doc_id = d.doc_id
               WHERE d.convert_status != 'failed' AND e.status = 'missing' GROUP BY d.ext ORDER BY d.ext"""
        ).fetchall()
        unreadable = connection.execute(
            """SELECT ext, COUNT(*) AS count FROM documents WHERE convert_status = 'failed'
               GROUP BY ext ORDER BY ext"""
        ).fetchall()
    by_format: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = by_format.setdefault(row["ext"], {"found": 0, "blank": 0, "missing": 0})
        bucket[row["status"]] = row["count"]
    with database(settings.database_path) as connection:
        indexed = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        extracted = connection.execute("SELECT COUNT(DISTINCT doc_id) FROM extractions").fetchone()[0]
    return {
        "formats": by_format,
        "documents": {"indexed": indexed, "comparable": extracted, "excluded_wrong_type": indexed - extracted},
        "readable_missing": {row["ext"]: row["count"] for row in readable_missing},
        "unreadable_documents": {row["ext"]: row["count"] for row in unreadable},
        "unknown_labels": [{"label": row["label"], "count": row["count"]} for row in unknown],
    }


def write_reports(settings: Settings) -> dict:
    report = coverage_report(settings)
    settings.derived_dir.mkdir(parents=True, exist_ok=True)
    coverage = {
        "documents": report["documents"],
        "formats": report["formats"],
        "readable_missing": report["readable_missing"],
        "unreadable_documents": report["unreadable_documents"],
    }
    (settings.derived_dir / "extraction_coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (settings.derived_dir / "unknown_labels.json").write_text(json.dumps(report["unknown_labels"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
