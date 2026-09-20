"""Write the current pipeline verdicts in the participant submission shape."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.submission import submission_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "submission.json")
    args = parser.parse_args()
    settings = settings_from_env()
    rows = submission_rows(settings.database_path)
    args.output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} records to {args.output}")


if __name__ == "__main__":
    main()
