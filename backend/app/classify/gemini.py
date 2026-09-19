"""Optional Gemini fallback with caching, validation and injection boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .features import EmailFeatures
from .rules import CATEGORIES


PROMPT_VERSION = "classification-v1"
SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
_limiter_lock = threading.Lock()
_request_times: list[float] = []
_token_events: list[tuple[float, int]] = []
_day = ""
_day_requests = 0


@dataclass(frozen=True)
class GeminiDecision:
    category: str
    confidence: float
    reason: str
    cached: bool


def _payload(features: EmailFeatures) -> dict:
    return {
        "sender": features.sender, "sender_domain": features.sender_domain,
        "subject": features.subject, "body": features.body,
        "attachments": [{"extension": item.extension, "detected_role": item.role or "unknown"} for item in features.attachments],
    }


def _validated(value: object, *, cached: bool) -> GeminiDecision | None:
    if not isinstance(value, dict):
        return None
    category, confidence, reason = value.get("category"), value.get("confidence"), value.get("reason")
    if category not in CATEGORIES or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return None
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        return None
    return GeminiDecision(category, float(confidence), reason.strip(), cached)


def _integer_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _reserve_budget(estimated_input_tokens: int) -> bool:
    """A process-local sliding-window limiter for the configured free-tier budget."""
    global _day, _day_requests
    rpm = _integer_env("GEMINI_MAX_RPM", 12)
    tpm = _integer_env("GEMINI_MAX_TPM", 200000)
    rpd = _integer_env("GEMINI_MAX_RPD", 1200)
    while True:
        with _limiter_lock:
            now = time.monotonic()
            current_day = time.strftime("%Y-%m-%d", time.gmtime())
            if current_day != _day:
                _day, _day_requests = current_day, 0
            _request_times[:] = [moment for moment in _request_times if now - moment < 60]
            _token_events[:] = [(moment, count) for moment, count in _token_events if now - moment < 60]
            tokens_used = sum(count for _, count in _token_events)
            if _day_requests >= rpd or estimated_input_tokens > tpm:
                return False
            if len(_request_times) < rpm and tokens_used + estimated_input_tokens <= tpm:
                _request_times.append(now)
                _token_events.append((now, estimated_input_tokens))
                _day_requests += 1
                return True
            waits = []
            if len(_request_times) >= rpm:
                waits.append(60 - (now - _request_times[0]))
            if tokens_used + estimated_input_tokens > tpm and _token_events:
                waits.append(60 - (now - _token_events[0][0]))
        time.sleep(max(0.01, min(waits) if waits else 0.01))


def _log_call(derived_dir: Path, email_id: str, *, cached: bool, latency_ms: int) -> None:
    log_path = derived_dir / "gemini_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"email_id": email_id, "purpose": "classification", "cached": cached, "latency_ms": latency_ms}
    with log_path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(entry, sort_keys=True) + "\n")


def classify(features: EmailFeatures, derived_dir: Path) -> GeminiDecision | None:
    """Call only with explicit configuration; disabled mode never makes a request."""
    if os.getenv("GEMINI_ENABLED", "false").lower() != "true":
        return None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    encoded = json.dumps(_payload(features), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{model}:{PROMPT_VERSION}:{encoded}".encode("utf-8")).hexdigest()
    cache_path = derived_dir / "gemini_cache" / "classification" / f"{digest}.json"
    try:
        cached = _validated(json.loads(cache_path.read_text(encoding="utf-8")), cached=True)
        if cached is not None:
            _log_call(derived_dir, features.email_id, cached=True, latency_ms=0)
        return cached
    except (OSError, json.JSONDecodeError):
        pass

    if not _reserve_budget(max(1, len(encoded) // 4)):
        return None

    request_body = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": "UNTRUSTED_EMAIL_DATA_BEGIN\n" + encoded + "\nUNTRUSTED_EMAIL_DATA_END"}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }).encode("utf-8")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    started = time.monotonic()
    for attempt in range(3):
        try:
            request = urllib.request.Request(endpoint, data=request_body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310: fixed Google endpoint
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            decision = _validated(json.loads(text), cached=False)
            if decision is None:
                return None
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"category": decision.category, "confidence": decision.confidence, "reason": decision.reason}) + "\n", encoding="utf-8")
            _log_call(derived_dir, features.email_id, cached=False, latency_ms=round((time.monotonic() - started) * 1000))
            return decision
        except (OSError, KeyError, IndexError, TypeError, ValueError, urllib.error.URLError):
            if attempt == 2:
                return None
            time.sleep(2 ** attempt)
    return None
