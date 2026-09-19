"""Request every attachment preview and verify the Phase 3 viewer contract."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.main import create_app
from backend.app.config import settings_from_env
from backend.app.db import database


KNOWN_CORRUPT = {"email_511_BL", "email_515_BL"}


def main() -> None:
    settings = settings_from_env()
    app = create_app()
    app.testing = True
    client = app.test_client()
    with database(settings.database_path) as connection:
        document_ids = [row["doc_id"] for row in connection.execute("SELECT doc_id FROM documents")]

    unreadable: set[str] = set()
    scans = 0
    for document_id in document_ids:
        response = client.get(f"/api/documents/{document_id}/preview")
        if response.status_code != 200:
            raise SystemExit(f"{document_id}: preview returned HTTP {response.status_code}")
        preview = response.get_json()
        if preview.get("error") == "unreadable":
            unreadable.add(document_id)
            continue
        if preview.get("metadata", {}).get("classification") == "scan":
            scans += 1
            page = preview["original"]["pages"][0]
            if client.get(page).mimetype != "image/png":
                raise SystemExit(f"{document_id}: scan page image was unavailable")

    if unreadable != KNOWN_CORRUPT:
        raise SystemExit(f"Unexpected unreadable files: {sorted(unreadable)}")
    if scans == 0:
        raise SystemExit("No scanned PDFs were detected")
    print(f"Previewed {len(document_ids)} documents: {scans} scans and {len(unreadable)} known corrupt PDFs.")


if __name__ == "__main__":
    main()
