from __future__ import annotations

import re


def normalize_party(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    value = value.upper().replace("&", " AND ")
    return re.sub(r"\s+", " ", re.sub(r"[.,;:()\-_/|]", " ", value)).strip() or None
