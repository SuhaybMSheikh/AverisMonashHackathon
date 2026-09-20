"""Submit a validated full submission only when an organizer server is explicitly supplied."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from backend.app.config import PROJECT_ROOT
from backend.app.loader import Inbox
from backend.app.submission import validate_submission


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="Organizer server, e.g. http://localhost:8080")
    parser.add_argument("--submission", type=Path, default=PROJECT_ROOT / "submission.json")
    parser.add_argument("--change", required=True, help="Human-readable meaningful change being evaluated")
    args = parser.parse_args()
    rows = json.loads(args.submission.read_text(encoding="utf-8"))
    validate_submission(rows, PROJECT_ROOT / "data" / "sample_submission.json")
    result = Inbox(args.server).submit(rows)
    log = PROJECT_ROOT / "docs" / "score_log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text("# Score log\n\n| Date | Change | Result | Notes |\n| --- | --- | --- | --- |\n", encoding="utf-8")
    with log.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"| {date.today().isoformat()} | {args.change.replace('|', '/')} | `{json.dumps(result, sort_keys=True)}` | Full validated submission; no single-email probing. |\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
