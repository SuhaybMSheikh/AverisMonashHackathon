"""Idempotently index the immutable participant bundle into SQLite."""
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..config import Settings, settings_from_env
from ..db import database, initialize
from ..loader import Inbox


@dataclass(frozen=True)
class IngestResult:
    emails: int
    documents: int


def attachment_path(data_dir: Path, stored_path: str) -> Path:
    """Resolve an attachment path, rejecting paths outside data/attachments/."""
    relative = PurePosixPath(stored_path.replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or relative.parts[0] != "attachments":
        raise FileNotFoundError("attachment path is outside data/attachments")

    candidate = (data_dir / Path(*relative.parts)).resolve()
    attachment_root = (data_dir / "attachments").resolve()
    try:
        candidate.relative_to(attachment_root)
    except ValueError as error:
        raise FileNotFoundError("attachment path is outside data/attachments") from error
    if not candidate.is_file():
        raise FileNotFoundError("attachment does not exist")
    return candidate


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def role_hint(path: Path) -> str | None:
    stem = path.stem.upper()
    if stem.endswith("_SI"):
        return "SI"
    if stem.endswith("_BL"):
        return "BL"
    return None


def ingest(settings: Settings, *, reset: bool = False) -> IngestResult:
    """Upsert emails/documents without reading or storing attachment contents."""
    if reset and settings.database_path.exists():
        settings.database_path.unlink()
    initialize(settings.database_path)
    inbox = Inbox(settings.data_dir)
    emails = inbox.emails()
    seen_documents: set[str] = set()

    with database(settings.database_path) as connection:
        for email in emails:
            connection.execute(
                """
                INSERT INTO emails (email_id, from_addr, subject, body, category)
                VALUES (:email_id, :from_addr, :subject, :body, 'UNCLASSIFIED')
                ON CONFLICT(email_id) DO UPDATE SET
                    from_addr = excluded.from_addr,
                    subject = excluded.subject,
                    body = excluded.body
                """,
                {
                    "email_id": email["email_id"],
                    "from_addr": email.get("from", ""),
                    "subject": email.get("subject", ""),
                    "body": email.get("body", ""),
                },
            )

            for stored_path in email.get("attachments", []):
                relative_path = PurePosixPath(stored_path.replace("\\", "/"))
                source_path = (settings.data_dir / Path(*relative_path.parts)).resolve()
                doc_id = source_path.stem
                seen_documents.add(doc_id)
                exists = source_path.is_file()
                connection.execute(
                    """
                    INSERT INTO documents (doc_id, email_id, path, ext, size, sha256, role_hint)
                    VALUES (:doc_id, :email_id, :path, :ext, :size, :sha256, :role_hint)
                    ON CONFLICT(doc_id) DO UPDATE SET
                        email_id = excluded.email_id,
                        path = excluded.path,
                        ext = excluded.ext,
                        size = excluded.size,
                        sha256 = excluded.sha256,
                        role_hint = excluded.role_hint
                    """,
                    {
                        "doc_id": doc_id,
                        "email_id": email["email_id"],
                        "path": PurePosixPath(stored_path.replace("\\", "/")).as_posix(),
                        "ext": source_path.suffix.lower(),
                        "size": source_path.stat().st_size if exists else 0,
                        "sha256": sha256(source_path) if exists else f"missing:{relative_path.as_posix()}",
                        "role_hint": role_hint(source_path),
                    },
                )

        # Every known email has an explicit lifecycle from the first ingest;
        # later stage executions replace pending with running/ok/failed/review.
        for email in emails:
            for stage in ("convert", "classify", "extract", "compare"):
                connection.execute(
                    "INSERT OR IGNORE INTO stage_runs (email_id, stage, state) VALUES (?, ?, 'pending')",
                    (email["email_id"], stage),
                )

        existing_documents = {
            row["doc_id"] for row in connection.execute("SELECT doc_id FROM documents")
        }
        for doc_id in existing_documents - seen_documents:
            connection.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))

        return IngestResult(
            emails=connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0],
            documents=connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete and rebuild the SQLite index")
    args = parser.parse_args()
    result = ingest(settings_from_env(), reset=args.reset)
    print(f"Indexed {result.emails} emails and {result.documents} documents.")


if __name__ == "__main__":
    main()
