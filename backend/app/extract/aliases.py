"""Conservative label aliases for the seven comparison fields."""
from __future__ import annotations

import re
from difflib import SequenceMatcher


ALIASES = {
    "shipper": ("shipper", "shipper exporter", "shipper principal or seller"),
    "consignee": ("consignee", "consignee non negotiable", "to the order of"),
    "notify_party": ("notify", "notify party", "notify party intermediate consignee"),
    "port_of_loading": ("port of loading", "port of loading pol", "pol", "load port"),
    "port_of_discharge": ("port of discharge", "port of discharge pod", "pod", "discharge port"),
    "container_count": ("total containers", "no of containers", "no of containers or packages", "container count"),
    "gross_weight_kg": (
        "gross wt kgs", "gross wt kgs kgs", "gross weight", "gross weight kg", "gross weight kgs",
        "gross weight kgs kgs", "total gross wt kgs", "total gross weight", "total gross weight kg",
    ),
}

FIELDS = tuple(ALIASES)


def normalize_label(label: str) -> str:
    """Apply the roadmap's label-only matching normalization."""
    value = re.sub(r"[\u3400-\u9fff]", "", label.lower())
    value = re.sub(r"\(\s*\)|\[\s*\]|\{\s*\}", "", value)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


_EXACT = {normalize_label(alias): field for field, aliases in ALIASES.items() for alias in aliases}


def resolve(label: str, *, threshold: float = 0.93) -> tuple[str | None, float]:
    """Return a field only for exact or very-high-confidence alias matches."""
    cleaned = normalize_label(label)
    if not cleaned:
        return None, 0.0
    if cleaned in _EXACT:
        return _EXACT[cleaned], 1.0
    scores = [(SequenceMatcher(None, cleaned, alias).ratio(), field) for alias, field in _EXACT.items()]
    score, field = max(scores, default=(0.0, None))
    return (field, score) if score >= threshold else (None, score)
