"""Read-only Flask API over the Phase 1 SQLite data layer."""
from __future__ import annotations

import mimetypes
import json
import re
import sqlite3
from flask import Flask, abort, jsonify, request, send_file

from .config import Settings, settings_from_env
from .db import database, initialize
from .extract.aliases import FIELDS
from .extract.pipeline import extract_text
from .pipeline.ingest import attachment_path, ingest
from .preview import preview_document, rendered_pdf_page


VALID_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
VALID_CATEGORIES = frozenset({"BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"})


def _integer_argument(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = request.args.get(name, default=default, type=int)
    if value is None or not minimum <= value <= maximum:
        abort(400, description=f"{name} must be between {minimum} and {maximum}")
    return value


def _snippet(body: str, limit: int = 180) -> str:
    compact = " ".join(body.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _presentation_meta(category: str, subject: str, body: str, reasons: str | None) -> dict:
    """Cheap, deterministic metadata for the non-comparison section cards."""
    if category == "SI_REQUEST":
        fields, _ = extract_text(body, "email_body")
        values = {field.field: field.raw for field in fields if field.status == "found"}
        route = " → ".join(value for value in (values.get("port_of_loading"), values.get("port_of_discharge")) if value)
        reference = re.search(r"\b(?:booking(?:\s+(?:no\.?|number|ref))?|order(?:\s+no\.?)?|reference)\s*[:#-]?\s*([A-Z0-9-]{4,})", body, re.I)
        missing = [field.field for field in fields if field.status != "found"]
        return {"route": route or None, "reference": reference.group(1) if reference else None, "missing_fields": missing}
    if category == "INVOICE_QUERY":
        invoice = re.search(r"\binvoice(?:\s*(?:no\.?|number))?\s*[:#-]?\s*([A-Z0-9-]{4,})", f"{subject}\n{body}", re.I)
        topic = "THC" if re.search(r"\bthc\b", body, re.I) else "Local charges" if re.search(r"local charges?", body, re.I) else "Other"
        return {"invoice_number": invoice.group(1) if invoice else None, "topic": topic}
    if category == "GENERAL":
        source = f"{subject}\n{body}".lower()
        notice = next((label for token, label in (("berthing", "Berthing report"), ("reminder", "Reminder"), ("outstanding", "Outstanding list"), ("update", "Update")) if token in source), "Notice")
        return {"notice_type": notice, "summary": _snippet(body, 110)}
    if category == "SPAM":
        try:
            why = json.loads(reasons or "[]")
        except json.JSONDecodeError:
            why = []
        return {"why_flagged": why}
    return {}


def _ensure_index(settings: Settings) -> None:
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        indexed = connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    if not indexed:
        ingest(settings)


def _not_found(_: Exception):
    return jsonify({"error": "not_found"}), 404


def _document(settings: Settings, doc_id: str) -> dict | None:
    if not VALID_DOCUMENT_ID.fullmatch(doc_id):
        return None
    with database(settings.database_path) as connection:
        row = connection.execute(
            """
            SELECT doc_id, path, ext, size, sha256, role_hint, convert_status, text_path
            FROM documents WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def _canonical_text(settings: Settings, stored_path: str | None) -> str | None:
    if not stored_path:
        return None
    candidate = (settings.derived_dir / stored_path).resolve()
    try:
        candidate.relative_to((settings.derived_dir / "text").resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate.read_text(encoding="utf-8")


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    settings = settings_from_env(overrides)
    app.config["SETTINGS"] = settings
    _ensure_index(settings)

    @app.errorhandler(404)
    def not_found(error):
        return _not_found(error)

    @app.route("/api/health", methods=["GET"])
    def health():
        try:
            with database(settings.database_path) as connection:
                emails = connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
                documents = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            return jsonify(
                {"status": "healthy", "database": "ready", "emails": emails, "documents": documents}
            )
        except sqlite3.Error:
            return jsonify({"status": "unhealthy", "database": "unavailable"}), 500

    @app.route("/api/emails/counts", methods=["GET"])
    def email_counts():
        categories = {name: 0 for name in ("BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM")}
        statuses = {name: 0 for name in ("OK", "MISMATCH", "NEEDS_REVIEW")}
        with database(settings.database_path) as connection:
            total = connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
            for row in connection.execute("SELECT COALESCE(category_override, category) AS category, COUNT(*) AS count FROM emails GROUP BY COALESCE(category_override, category)"):
                categories[row["category"]] = row["count"]
            for row in connection.execute(
                """SELECT c.status, COUNT(*) AS count FROM comparisons c
                   JOIN emails e ON e.email_id = c.email_id
                   WHERE COALESCE(e.category_override, e.category) = 'BL_COMPARISON' AND c.status IS NOT NULL GROUP BY c.status"""
            ):
                statuses[row["status"]] = row["count"]
        return jsonify({"all": total, "categories": categories, "statuses": statuses})

    @app.route("/api/emails", methods=["GET"])
    def list_emails():
        category = request.args.get("category")
        status = request.args.get("status")
        sort = request.args.get("sort")
        uncertain = request.args.get("uncertain")
        query = request.args.get("q", "").strip()
        page = _integer_argument("page", 1, minimum=1, maximum=10000)
        page_size = _integer_argument("page_size", 520, minimum=1, maximum=520)

        conditions: list[str] = []
        parameters: list[str] = []
        if category:
            conditions.append("COALESCE(e.category_override, e.category) = ?")
            parameters.append(category)
        if status:
            conditions.append("c.status = ?")
            parameters.append(status)
        if uncertain not in (None, "1"):
            abort(400, description="uncertain must be 1")
        if uncertain == "1":
            conditions.append("e.category_conf < 0.75")
        if query:
            like = f"%{query.lower()}%"
            conditions.append("(LOWER(e.from_addr) LIKE ? OR LOWER(e.subject) LIKE ? OR LOWER(e.body) LIKE ?)")
            parameters.extend([like, like, like])
        if sort not in (None, "mismatch_first"):
            abort(400, description="sort must be mismatch_first")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        joins = " FROM emails e LEFT JOIN comparisons c ON c.email_id = e.email_id"

        with database(settings.database_path) as connection:
            total = connection.execute("SELECT COUNT(*)" + joins + where, parameters).fetchone()[0]
            rows = connection.execute(
                """
                SELECT e.email_id, e.from_addr, e.subject, e.body, COALESCE(e.category_override, e.category) AS category, e.category AS detected_category, e.category_conf, e.category_reasons, e.decided_by, c.status,
                       c.review_reason, c.defect_fields,
                       EXISTS(SELECT 1 FROM reviews r WHERE r.email_id = e.email_id AND r.disposition = 'confirmed') AS reviewer_confirmed,
                       COUNT(d.doc_id) AS attachment_count, GROUP_CONCAT(d.ext) AS formats
                """
                + joins
                + " LEFT JOIN documents d ON d.email_id = e.email_id"
                + where
                + " GROUP BY e.email_id ORDER BY "
                + ("CASE c.status WHEN 'MISMATCH' THEN 0 WHEN 'NEEDS_REVIEW' THEN 1 WHEN 'OK' THEN 2 ELSE 3 END, e.email_id" if sort == "mismatch_first" else "e.email_id")
                + " LIMIT ? OFFSET ?",
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()

        payload = [
            {
                "email_id": row["email_id"],
                "from": row["from_addr"],
                "subject": row["subject"],
                "body_snippet": _snippet(row["body"]),
                "category": row["category"],
                "detected_category": row["detected_category"],
                "category_conf": row["category_conf"],
                "decided_by": row["decided_by"],
                "status": row["status"],
                "review_reason": row["review_reason"],
                "defect_fields": json.loads(row["defect_fields"] or "[]"),
                "reviewer_confirmed": bool(row["reviewer_confirmed"]),
                "display_meta": _presentation_meta(row["category"], row["subject"], row["body"], row["category_reasons"]),
                "attachment_count": row["attachment_count"],
                "formats": sorted(set(filter(None, (row["formats"] or "").split(",")))),
            }
            for row in rows
        ]
        response = jsonify(payload)
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)
        return response

    @app.route("/api/emails/<email_id>", methods=["GET"])
    def get_email(email_id: str):
        with database(settings.database_path) as connection:
            email = connection.execute(
                """
                SELECT e.email_id, e.from_addr, e.subject, e.body, COALESCE(e.category_override, e.category) AS category, e.category AS detected_category, e.category_conf,
                       e.category_reasons, e.decided_by, e.category_override, c.status
                FROM emails e LEFT JOIN comparisons c ON c.email_id = e.email_id
                WHERE e.email_id = ?
                """,
                (email_id,),
            ).fetchone()
            if email is None:
                abort(404)
            documents = connection.execute(
                "SELECT doc_id, ext, role_hint, convert_status FROM documents WHERE email_id = ? ORDER BY doc_id",
                (email_id,),
            ).fetchall()
        return jsonify(
            {
                "email_id": email["email_id"],
                "from": email["from_addr"],
                "subject": email["subject"],
                "body": email["body"],
                "category": email["category"],
                "detected_category": email["detected_category"],
                "category_conf": email["category_conf"],
                "category_reasons": email["category_reasons"],
                "decided_by": email["decided_by"],
                "category_override": email["category_override"],
                "status": email["status"],
                "documents": [dict(document) for document in documents],
            }
        )

    @app.route("/api/emails/<email_id>/category", methods=["POST"])
    def change_category(email_id: str):
        payload = request.get_json(silent=True)
        category = payload.get("category") if isinstance(payload, dict) else None
        if category not in VALID_CATEGORIES:
            abort(400, description="category must be one of the five inbox categories")
        with database(settings.database_path) as connection:
            email = connection.execute("SELECT category FROM emails WHERE email_id = ?", (email_id,)).fetchone()
            if email is None:
                abort(404)
            override = None if category == email["category"] else category
            connection.execute("UPDATE emails SET category_override = ? WHERE email_id = ?", (override, email_id))
            connection.execute("INSERT INTO audit_log (email_id, action, detail) VALUES (?, 'category_changed', ?)", (email_id, json.dumps({"category": category, "override": override})))
        return jsonify({"email_id": email_id, "category": category, "category_override": override})

    @app.route("/api/emails/<email_id>/body-fields", methods=["GET"])
    def body_fields(email_id: str):
        """Parse an SI request body with the same canonical field parser as attachments."""
        with database(settings.database_path) as connection:
            email = connection.execute(
                "SELECT body, COALESCE(category_override, category) AS category FROM emails WHERE email_id = ?", (email_id,)
            ).fetchone()
        if email is None:
            abort(404)
        if email["category"] != "SI_REQUEST":
            abort(400, description="body fields are available only for SI requests")
        fields, _ = extract_text(email["body"], f"{email_id}_body")
        return jsonify([{"field": field.field, "raw": field.raw, "normalized": field.normalized, "line_no": field.line_no, "status": field.status} for field in fields])

    @app.route("/api/emails/<email_id>/documents", methods=["GET"])
    def list_documents(email_id: str):
        with database(settings.database_path) as connection:
            exists = connection.execute("SELECT 1 FROM emails WHERE email_id = ?", (email_id,)).fetchone()
            if exists is None:
                abort(404)
            documents = connection.execute(
                """
                SELECT doc_id, email_id, path, ext, size, sha256, role_hint, role_detected,
                       convert_status, convert_method, text_path, meta_path
                FROM documents WHERE email_id = ? ORDER BY doc_id
                """,
                (email_id,),
            ).fetchall()
        return jsonify([dict(document) for document in documents])

    @app.route("/api/emails/<email_id>/comparison", methods=["GET"])
    def get_comparison(email_id: str):
        with database(settings.database_path) as connection:
            row = connection.execute(
                "SELECT email_id, status, review_reason, has_defect, defect_fields, field_results, explanations FROM comparisons WHERE email_id = ?",
                (email_id,),
            ).fetchone()
        if row is None:
            abort(404)
        comparison = dict(row)
        comparison["has_defect"] = bool(comparison["has_defect"])
        for field in ("defect_fields", "field_results", "explanations"):
            comparison[field] = json.loads(comparison[field] or "[]")
        with database(settings.database_path) as connection:
            comparison["reviews"] = [dict(item) for item in connection.execute(
                "SELECT id, doc_role, field, value, reviewer, note, disposition, created_at "
                "FROM reviews WHERE email_id = ? ORDER BY id", (email_id,)
            )]
        return jsonify(comparison)

    @app.route("/api/review-queue", methods=["GET"])
    def review_queue():
        """All currently unresolved comparison emails, grouped deterministically."""
        with database(settings.database_path) as connection:
            rows = connection.execute(
                """SELECT e.email_id, e.from_addr, e.subject, c.status, c.review_reason,
                          c.field_results, c.computed_at
                   FROM comparisons c JOIN emails e ON e.email_id = c.email_id
                   WHERE e.category = 'BL_COMPARISON' AND c.status = 'NEEDS_REVIEW'
                   ORDER BY c.review_reason, e.email_id"""
            ).fetchall()
        return jsonify([{
            **{key: row[key] for key in ("email_id", "from_addr", "subject", "status", "review_reason", "computed_at")},
            "field_results": json.loads(row["field_results"] or "[]"),
        } for row in rows])

    @app.route("/api/emails/<email_id>/review-context", methods=["GET"])
    def review_context(email_id: str):
        """Immutable extraction evidence for the human-review panel."""
        with database(settings.database_path) as connection:
            email = connection.execute("SELECT 1 FROM emails WHERE email_id = ?", (email_id,)).fetchone()
            if email is None:
                abort(404)
            rows = connection.execute(
                """SELECT d.doc_id, d.role_detected AS doc_role, d.convert_status, d.text_path,
                          e.field, e.raw, e.normalized, e.line_no, e.confidence, e.status
                   FROM documents d LEFT JOIN extractions e ON e.doc_id = d.doc_id
                   WHERE d.email_id = ? AND d.role_detected IN ('SI', 'BL')
                   ORDER BY d.role_detected, e.field""", (email_id,)
            ).fetchall()
        return jsonify([{
            **dict(row),
            "source_text_url": f"/api/documents/{row['doc_id']}/text" if row["convert_status"] != "failed" else None,
            "source_page_url": f"/api/documents/{row['doc_id']}/pages/1.png" if row["convert_status"] == "failed" else None,
        } for row in rows])

    @app.route("/api/emails/<email_id>/review", methods=["POST"])
    def save_review(email_id: str):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            abort(400, description="review must be a JSON object")
        field = payload.get("field")
        doc_role = payload.get("doc_role")
        disposition = payload.get("disposition", "confirmed")
        value = payload.get("value")
        reviewer = payload.get("reviewer", "")
        note = payload.get("note", "")
        if field not in FIELDS or doc_role not in {"SI", "BL"}:
            abort(400, description="field and doc_role must identify a comparison value")
        if disposition not in {"confirmed", "cannot_determine", "unreadable"}:
            abort(400, description="invalid review disposition")
        if not isinstance(reviewer, str) or not isinstance(note, str) or len(reviewer) > 120 or len(note) > 2000:
            abort(400, description="invalid reviewer or note")
        if disposition == "confirmed" and (not isinstance(value, str) or not value.strip() or len(value) > 2000):
            abort(400, description="a confirmed review requires a value")
        if disposition != "confirmed":
            value = None
            if not note.strip():
                abort(400, description="an unresolved review requires a note")
        with database(settings.database_path) as connection:
            email = connection.execute("SELECT category FROM emails WHERE email_id = ?", (email_id,)).fetchone()
            comparison = connection.execute("SELECT status FROM comparisons WHERE email_id = ?", (email_id,)).fetchone()
            document = connection.execute(
                "SELECT 1 FROM documents WHERE email_id = ? AND role_detected = ?", (email_id, doc_role)
            ).fetchone()
            if email is None:
                abort(404)
            if email["category"] != "BL_COMPARISON" or document is None or comparison is None or comparison["status"] != "NEEDS_REVIEW":
                abort(400, description="reviews apply only to an unresolved SI or draft BL comparison value")
            connection.execute(
                "INSERT INTO reviews (email_id, doc_role, field, value, reviewer, note, disposition) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (email_id, doc_role, field, value.strip() if isinstance(value, str) else None, reviewer.strip(), note.strip(), disposition),
            )
            connection.execute(
                "INSERT INTO audit_log (email_id, action, detail) VALUES (?, 'review_saved', ?)",
                (email_id, json.dumps({"field": field, "doc_role": doc_role, "disposition": disposition})),
            )
        from .compare import compare_email
        return jsonify(compare_email(settings, email_id))

    @app.route("/api/documents/<doc_id>/original", methods=["GET"])
    def get_original(doc_id: str):
        document = _document(settings, doc_id)
        if document is None:
            abort(404)
        try:
            source_path = attachment_path(settings.data_dir, document["path"])
        except FileNotFoundError:
            abort(404)
        return send_file(
            source_path,
            mimetype=mimetypes.guess_type(source_path.name)[0] or "application/octet-stream",
            as_attachment=request.args.get("download") == "1",
            download_name=source_path.name,
        )

    @app.route("/api/documents/<doc_id>/preview", methods=["GET"])
    def get_preview(doc_id: str):
        document = _document(settings, doc_id)
        if document is None:
            abort(404)
        try:
            source_path = attachment_path(settings.data_dir, document["path"])
        except FileNotFoundError:
            abort(404)
        canonical = _canonical_text(settings, document["text_path"]) if document["convert_status"] != "failed" else None
        return jsonify(preview_document(source_path, document, settings.derived_dir, canonical))

    @app.route("/api/documents/<doc_id>/text", methods=["GET"])
    def get_canonical_text(doc_id: str):
        document = _document(settings, doc_id)
        if document is None:
            abort(404)
        canonical = _canonical_text(settings, document["text_path"])
        if document["convert_status"] == "failed" or canonical is None:
            abort(404)
        return app.response_class(canonical, mimetype="text/plain")

    @app.route("/api/documents/<doc_id>/pages/<int:page_number>.png", methods=["GET"])
    def get_pdf_page(doc_id: str, page_number: int):
        document = _document(settings, doc_id)
        if document is None or document["ext"].lower() != ".pdf":
            abort(404)
        try:
            source_path = attachment_path(settings.data_dir, document["path"])
        except FileNotFoundError:
            abort(404)
        image_path = rendered_pdf_page(source_path, document, settings.derived_dir, page_number)
        if image_path is None:
            abort(404)
        return send_file(image_path, mimetype="image/png", conditional=True)

    return app


app = create_app()
