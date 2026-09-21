"""Build the self-contained, offline demo state used by the container image."""
from __future__ import annotations

import os
from pathlib import Path

from .config import PROJECT_ROOT, settings_from_env
from .db import database
from .pipeline.ingest import attachment_path
from .pipeline.runner import run_all
from .preview import rendered_pdf_page
from .reliability import export_snapshot


def prepare_demo() -> tuple[int, int]:
    """Run deterministic processing, export state, and warm PDF preview images."""
    settings = settings_from_env()
    run_all()
    configured_output = Path(os.getenv("RESULTS_SNAPSHOT_OUTPUT", "results_snapshot.json"))
    snapshot_output = configured_output if configured_output.is_absolute() else PROJECT_ROOT / configured_output
    export_snapshot(settings, snapshot_output)

    with database(settings.database_path) as connection:
        documents = [dict(row) for row in connection.execute(
            "SELECT doc_id, path, ext, size, role_hint FROM documents WHERE lower(ext) = '.pdf'"
        )]

    warmed = 0
    for document in documents:
        try:
            source = attachment_path(settings.data_dir, document["path"])
            if rendered_pdf_page(source, document, settings.derived_dir, 1) is not None:
                warmed += 1
        except (FileNotFoundError, OSError):
            # Unreadable participant attachments remain visible as such in the UI.
            continue
    return len(documents), warmed


def main() -> None:
    pdfs, warmed = prepare_demo()
    print(f"Prepared demo snapshot and warmed {warmed}/{pdfs} PDF previews.")


if __name__ == "__main__":
    main()
