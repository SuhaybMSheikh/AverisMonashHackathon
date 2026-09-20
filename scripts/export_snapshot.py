"""Export the fully persisted pipeline state for an offline demo."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings_from_env
from backend.app.reliability import export_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="JSON snapshot path (defaults to derived/results_snapshot.json)")
    args = parser.parse_args()
    settings = settings_from_env()
    print(export_snapshot(settings, None if not args.output else settings.derived_dir / args.output))


if __name__ == "__main__":
    main()
