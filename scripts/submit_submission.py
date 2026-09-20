"""Submit a validated full submission only when an organizer server is explicitly supplied."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backend.app.config import PROJECT_ROOT
from backend.app.submission import validate_submission
from loader import Inbox


SCORE_LOG = PROJECT_ROOT / "docs" / "score_log.md"
_LOGGED_SHA256 = re.compile(r"^- SHA-256: `([0-9a-f]{64})`$", re.MULTILINE)


def submission_sha256(path: Path) -> str:
    """Return the exact bytes hash that identifies a full submission."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def logged_submission_hashes(log_path: Path = SCORE_LOG) -> set[str]:
    """Read prior logged submissions without interpreting their score payloads."""
    try:
        return set(_LOGGED_SHA256.findall(log_path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return set()


def _commit() -> str:
    """Record the source revision used for the submission when Git is available."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def append_score_log(*, note: str, digest: str, result: object, log_path: Path = SCORE_LOG) -> None:
    """Append an auditable, complete server response for one full submission."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        if log_path.stat().st_size == 0:
            stream.write("# Score log\n")
        stream.write(
            f"\n## Submission — {timestamp}\n\n"
            f"- Date: {timestamp}\n"
            f"- Git commit: `{_commit()}`\n"
            f"- SHA-256: `{digest}`\n"
            f"- Note: {note}\n"
            "- Submission policy: full validated submission; no single-email probing.\n"
            "- Score response (all components returned by the organizer):\n\n"
            "```json\n"
            f"{json.dumps(result, indent=2, sort_keys=True)}\n"
            "```\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="Organizer server, e.g. http://localhost:8080")
    parser.add_argument("--submission", type=Path, default=PROJECT_ROOT / "submission.json")
    parser.add_argument("--note", required=True, help="Human-readable meaningful change being evaluated")
    args = parser.parse_args()
    args.note = " ".join(args.note.split())
    if not args.note:
        parser.error("--note must describe the submission")
    rows = json.loads(args.submission.read_text(encoding="utf-8"))
    validate_submission(rows, PROJECT_ROOT / "data" / "sample_submission.json")
    digest = submission_sha256(args.submission)
    if digest in logged_submission_hashes():
        parser.error("refusing duplicate submission: this submission SHA-256 is already in docs/score_log.md")
    result = Inbox(args.server).submit(rows)
    append_score_log(note=args.note, digest=digest, result=result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
