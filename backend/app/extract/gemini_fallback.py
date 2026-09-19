"""Optional, cached alias discovery for genuinely unknown labels.

No attachment values are sent: this is deliberately limited to labels that the
deterministic alias table did not recognize.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .aliases import FIELDS, normalize_label


def _cache_path(derived_dir: Path) -> Path:
    return derived_dir / "learned_aliases.json"


def learned_aliases(derived_dir: Path) -> dict[str, str]:
    try:
        value = json.loads(_cache_path(derived_dir).read_text(encoding="utf-8"))
        return {key: field for key, field in value.items() if isinstance(key, str) and field in FIELDS}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def resolve(labels: list[str], derived_dir: Path) -> dict[str, str]:
    """Return approved mappings, using Gemini only after an explicit opt-in."""
    cached = learned_aliases(derived_dir)
    result = {label: cached[normalized] for label in labels if (normalized := normalize_label(label)) in cached}
    pending = [label for label in labels if label not in result]
    if not pending or os.getenv("GEMINI_ENABLED", "false").lower() != "true" or not os.getenv("GEMINI_API_KEY"):
        return result

    prompt = (
        "Map each shipping-document LABEL to one of " + json.dumps(FIELDS) +
        " or null. Use only the label; never infer from a value. Return a JSON object whose keys are exactly the input labels."
    )
    body = json.dumps({
        "system_instruction": {"parts": [{"text": prompt}]},
        "contents": [{"role": "user", "parts": [{"text": "UNTRUSTED_LABELS_BEGIN\n" + json.dumps(pending) + "\nUNTRUSTED_LABELS_END"}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }).encode("utf-8")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={os.environ['GEMINI_API_KEY']}"
    try:
        request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310: fixed Google endpoint
            payload = json.loads(response.read().decode("utf-8"))
        proposed = json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
    except (OSError, ValueError, KeyError, IndexError, TypeError, urllib.error.URLError):
        return result
    if not isinstance(proposed, dict):
        return result
    for label in pending:
        field = proposed.get(label)
        if field in FIELDS:
            result[label] = field
            cached[normalize_label(label)] = field
    if cached:
        _cache_path(derived_dir).parent.mkdir(parents=True, exist_ok=True)
        _cache_path(derived_dir).write_text(json.dumps(cached, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
