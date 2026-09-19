from __future__ import annotations

import re


_COUNT = re.compile(r"^\s*(\d+)\b")


def normalize_container_count(value: str) -> str | None:
    match = _COUNT.match(value)
    return match.group(1) if match else None
