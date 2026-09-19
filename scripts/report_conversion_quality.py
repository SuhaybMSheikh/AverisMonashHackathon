"""Report the preliminary seven-field coverage of Phase 4 canonical text."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings_from_env
from backend.app.db import database
from backend.app.pipeline.convert import SEVEN_FIELDS, canonical_fields


def main() -> None:
    settings = settings_from_env()
    with database(settings.database_path) as connection:
        documents = [dict(row) for row in connection.execute("SELECT doc_id, convert_status, text_path FROM documents ORDER BY doc_id")]
    incomplete: list[tuple[str, list[str]]] = []
    for document in documents:
        if document["convert_status"] == "failed" or not document["text_path"]:
            incomplete.append((document["doc_id"], sorted(SEVEN_FIELDS)))
            continue
        text = (settings.derived_dir / document["text_path"]).read_text(encoding="utf-8")
        missing = sorted(set(SEVEN_FIELDS) - set(canonical_fields(text)))
        if missing:
            incomplete.append((document["doc_id"], missing))
    print(f"Canonical field coverage: {len(documents) - len(incomplete)}/{len(documents)} complete seven-field records.")
    for document_id, missing in incomplete:
        print(f"{document_id}: missing {', '.join(missing)}")


if __name__ == "__main__":
    main()
