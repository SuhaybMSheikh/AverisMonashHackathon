from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


_NUMBER = re.compile(r"([0-9][0-9,]*(?:\.\d+)?)")


def normalize_weight_kg(value: str) -> str | None:
    match = _NUMBER.search(value.replace(" ", ""))
    if not match:
        return None
    try:
        weight = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    if re.search(r"\b(?:MT|TONS?)\b", value, re.I):
        weight *= 1000
    rendered = format(weight, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
