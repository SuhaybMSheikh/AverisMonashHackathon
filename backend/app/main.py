"""Read-only Flask API over the Phase 1 SQLite data layer."""
from __future__ import annotations

import mimetypes
import re
import sqlite3
from flask import Flask, abort, jsonify, request, send_file

from .config import Settings, settings_from_env
from .db import database, initialize
from .pipeline.ingest import attachment_path, ingest


VALID_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def _integer_argument(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = request.args.get(name, default=default, type=int)
    if value is None or not minimum <= value <= maximum:
        abort(400, description=f"{name} must be between {minimum} and {maximum}")
    return value


def _snippet(body: str, limit: int = 180) -> str:
    compact = " ".join(body.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _ensure_index(settings: Settings) -> None:
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        indexed = connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    if not indexed:
        ingest(settings)


def _not_found(_: Exception):
    return jsonify({"error": "not_found"}), 404


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

    @app.route("/api/emails", methods=["GET"])
    def list_emails():
        category = request.args.get("category")
        status = request.args.get("status")
        query = request.args.get("q", "").strip()
        page = _integer_argument("page", 1, minimum=1, maximum=10000)
        page_size = _integer_argument("page_size", 520, minimum=1, maximum=520)

        conditions: list[str] = []
        parameters: list[str] = []
        if category:
            conditions.append("e.category = ?")
            parameters.append(category)
        if status:
            conditions.append("c.status = ?")
            parameters.append(status)
        if query:
            like = f"%{query.lower()}%"
            conditions.append("(LOWER(e.from_addr) LIKE ? OR LOWER(e.subject) LIKE ? OR LOWER(e.body) LIKE ?)")
            parameters.extend([like, like, like])
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        joins = " FROM emails e LEFT JOIN comparisons c ON c.email_id = e.email_id"

        with database(settings.database_path) as connection:
            total = connection.execute("SELECT COUNT(*)" + joins + where, parameters).fetchone()[0]
            rows = connection.execute(
                """
                SELECT e.email_id, e.from_addr, e.subject, e.body, e.category, c.status,
                       COUNT(d.doc_id) AS attachment_count, GROUP_CONCAT(d.ext) AS formats
                """
                + joins
                + " LEFT JOIN documents d ON d.email_id = e.email_id"
                + where
                + " GROUP BY e.email_id ORDER BY e.email_id LIMIT ? OFFSET ?",
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()

        payload = [
            {
                "email_id": row["email_id"],
                "from": row["from_addr"],
                "subject": row["subject"],
                "body_snippet": _snippet(row["body"]),
                "category": row["category"],
                "status": row["status"],
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
                SELECT e.email_id, e.from_addr, e.subject, e.body, e.category, e.category_conf,
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
                "category_conf": email["category_conf"],
                "category_reasons": email["category_reasons"],
                "decided_by": email["decided_by"],
                "category_override": email["category_override"],
                "status": email["status"],
                "documents": [dict(document) for document in documents],
            }
        )

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

    @app.route("/api/documents/<doc_id>/original", methods=["GET"])
    def get_original(doc_id: str):
        if not VALID_DOCUMENT_ID.fullmatch(doc_id):
            abort(404)
        with database(settings.database_path) as connection:
            document = connection.execute(
                "SELECT path FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        if document is None:
            abort(404)
        try:
            source_path = attachment_path(settings.data_dir, document["path"])
        except FileNotFoundError:
            abort(404)
        return send_file(
            source_path,
            mimetype=mimetypes.guess_type(source_path.name)[0] or "application/octet-stream",
            as_attachment=False,
            download_name=source_path.name,
        )

    return app


app = create_app()
