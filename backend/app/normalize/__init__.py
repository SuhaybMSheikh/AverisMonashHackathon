"""Canonical comparison-value normalizers."""

from .containers import normalize_container_count
from .parties import normalize_party
from .ports import normalize_port
from .weight import normalize_weight_kg


def normalize(field: str, raw: str) -> str | None:
    if field in {"shipper", "consignee", "notify_party"}:
        return normalize_party(raw)
    if field in {"port_of_loading", "port_of_discharge"}:
        return normalize_port(raw)
    if field == "container_count":
        return normalize_container_count(raw)
    if field == "gross_weight_kg":
        return normalize_weight_kg(raw)
    raise ValueError(f"unknown field: {field}")
