"""Build the self-contained, offline demo state used by the container image."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT, Settings, settings_from_env
from .db import database
from .pipeline.ingest import attachment_path
from .pipeline.runner import run_all
from .preview import preview_document
from .reliability import export_snapshot


@dataclass(frozen=True)
class SkippedDocument:
    document_id: str
    filename: str
    reason: str


@dataclass(frozen=True)
class PrecomputeSummary:
    documents_processed: int
    documents_rendered: int
    pages_rendered: int
    skipped: tuple[SkippedDocument, ...]

    def report(self) -> str:
        lines = [
            f"Documents processed: {self.documents_processed}",
            f"Documents rendered: {self.documents_rendered}",
            f"Pages rendered: {self.pages_rendered}",
        ]
        if self.skipped:
            lines.append("Skipped documents:")
            lines.extend(f"- {item.document_id} ({item.filename}): {item.reason}" for item in self.skipped)
        else:
            lines.append("Skipped documents: none")
        return "\n".join(lines)


def _skip_reason(document: dict, preview: dict) -> str:
    """Map the API's safe preview classification to build diagnostics."""
    error_type = preview.get("metadata", {}).get("error_type")
    if error_type in {"PermissionError", "OSError"}:
        raise RuntimeError(f"unable to write PDF preview cache for {document['doc_id']}: {error_type}")
    if preview.get("metadata", {}).get("classification") == "corrupt":
        return "corrupt_pdf" if document["ext"].lower() == ".pdf" else "corrupt_document"
    return preview.get("error") or "preview_unavailable"


def warm_pdf_previews(settings: Settings) -> PrecomputeSummary:
    """Warm every PDF page cache without allowing one untrusted file to abort it."""
    try:
        (settings.derived_dir / "pages").mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeError(f"unable to create PDF preview cache directory: {error}") from error

    with database(settings.database_path) as connection:
        documents = [dict(row) for row in connection.execute(
            "SELECT doc_id, path, ext, size, role_hint FROM documents WHERE lower(ext) = '.pdf'"
        )]

    rendered = 0
    pages_rendered = 0
    skipped: list[SkippedDocument] = []
    for document in documents:
        try:
            source = attachment_path(settings.data_dir, document["path"])
        except FileNotFoundError:
            skipped.append(SkippedDocument(document["doc_id"], Path(document["path"]).name, "missing_attachment"))
            continue

        preview = preview_document(source, document, settings.derived_dir)
        if preview.get("error"):
            skipped.append(SkippedDocument(document["doc_id"], Path(document["path"]).name, _skip_reason(document, preview)))
            continue

        pages = preview.get("original", {}).get("pages", [])
        rendered += 1
        pages_rendered += len(pages)

    summary = PrecomputeSummary(len(documents), rendered, pages_rendered, tuple(skipped))
    if not summary.documents_rendered:
        raise RuntimeError(f"zero PDF documents rendered\n{summary.report()}")
    return summary


def prepare_demo(
    settings: Settings | None = None,
    *,
    run_pipeline: bool = True,
    snapshot_output: Path | None = None,
) -> PrecomputeSummary:
    """Run deterministic processing, export state, and warm PDF preview images."""
    settings = settings or settings_from_env()
    if run_pipeline:
        run_all()
    if snapshot_output is None:
        configured_output = Path(os.getenv("RESULTS_SNAPSHOT_OUTPUT", "results_snapshot.json"))
        snapshot_output = configured_output if configured_output.is_absolute() else PROJECT_ROOT / configured_output
    export_snapshot(settings, snapshot_output)
    return warm_pdf_previews(settings)


def main() -> None:
    print(prepare_demo().report())


if __name__ == "__main__":
    main()
