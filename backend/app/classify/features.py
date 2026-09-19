"""Features available to the classifier without treating email text as commands."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AttachmentFeature:
    doc_id: str
    extension: str
    role: str | None


@dataclass(frozen=True)
class EmailFeatures:
    email_id: str
    subject: str
    body: str
    sender: str
    sender_domain: str
    attachments: tuple[AttachmentFeature, ...]

    @property
    def attachment_count(self) -> int:
        return len(self.attachments)

    @property
    def attachment_types(self) -> tuple[str, ...]:
        return tuple(sorted({attachment.extension for attachment in self.attachments}))

    @property
    def detected_roles(self) -> tuple[str, ...]:
        return tuple(attachment.role or "unknown" for attachment in self.attachments)


def sender_domain(sender: str) -> str:
    """Return the address domain only; malformed addresses deliberately have none."""
    candidate = sender.rsplit("@", 1)
    return candidate[1].strip().lower() if len(candidate) == 2 and "." in candidate[1] else ""


def detected_role(document: dict, derived_dir: Path) -> str | None:
    """Prefer Phase 4's content-derived role over the filename hint."""
    role = document.get("role_detected")
    if role in {"SI", "BL"}:
        return role
    meta_path = document.get("meta_path")
    if meta_path:
        candidate = (derived_dir / meta_path).resolve()
        try:
            candidate.relative_to((derived_dir / "meta").resolve())
            metadata = json.loads(candidate.read_text(encoding="utf-8"))
            if metadata.get("role") in {"SI", "BL"}:
                return metadata["role"]
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return None


def build_features(email: dict, documents: list[dict], derived_dir: Path) -> EmailFeatures:
    attachments = tuple(
        AttachmentFeature(document["doc_id"], document["ext"].lower(), detected_role(document, derived_dir))
        for document in documents
    )
    return EmailFeatures(email["email_id"], email["subject"], email["body"], email["from_addr"], sender_domain(email["from_addr"]), attachments)
