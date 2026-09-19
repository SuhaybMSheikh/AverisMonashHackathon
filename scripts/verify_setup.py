"""Read-only Phase 0 repository and participant-bundle verification."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
INBOX_DIR = DATA_DIR / "inbox"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
SAMPLE_SUBMISSION = DATA_DIR / "sample_submission.json"
REQUIRED_ENV_KEYS = {
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_MAX_RPM",
    "GEMINI_MAX_TPM",
    "GEMINI_MAX_RPD",
    "DATA_DIR",
    "DERIVED_DIR",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for path in (DATA_DIR, INBOX_DIR, ATTACHMENTS_DIR, SAMPLE_SUBMISSION):
        if not path.exists():
            fail(f"missing required path: {path.relative_to(ROOT)}")

    emails = sorted(INBOX_DIR.glob("email_*.json"))
    if len(emails) != 520:
        fail(f"expected 520 inbox records, found {len(emails)}")

    attachment_count = sum(1 for path in ATTACHMENTS_DIR.iterdir() if path.is_file())
    if attachment_count != 250:
        fail(f"expected 250 attachments, found {attachment_count}")

    first_email = json.loads(emails[0].read_text(encoding="utf-8"))
    if set(first_email) != {"email_id", "from", "subject", "body", "attachments"}:
        fail("email JSON schema does not match the participant bundle contract")

    submission = json.loads(SAMPLE_SUBMISSION.read_text(encoding="utf-8"))
    if len(submission) != 520:
        fail(f"expected 520 sample-submission entries, found {len(submission)}")

    env_example = ROOT / ".env.example"
    keys = {
        line.partition("=")[0]
        for line in env_example.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    missing_keys = REQUIRED_ENV_KEYS - keys
    if missing_keys:
        fail(f".env.example is missing: {', '.join(sorted(missing_keys))}")

    print("Phase 0 setup verified: 520 emails, 250 attachments, and safe configuration present.")


if __name__ == "__main__":
    main()
