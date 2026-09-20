from __future__ import annotations

import re


def _normalize(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    value = value.upper().replace("&", " AND ")
    return re.sub(r"\s+", " ", re.sub(r"[.,;:()\-_/|]", " ", value)).strip() or None


def normalize_party(value: str) -> str | None:
    return _normalize(value)


def split_party(value: str | None) -> tuple[str | None, str | None]:
    """Return normalized party name and optional address from canonical multiline text."""
    if not value:
        return None, None
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return None, None
    return _normalize(lines[0]), _normalize(" ".join(lines[1:])) if len(lines) > 1 else None
