from __future__ import annotations

import re


def normalize_port(value: str) -> str | None:
    value = re.sub(r"\s*\([A-Z]{2}[A-Z0-9]{3}\)\s*$", "", value.strip().upper())
    return re.sub(r"\s+", " ", re.sub(r"[.,;:()\-_/|]", " ", value)).strip() or None
