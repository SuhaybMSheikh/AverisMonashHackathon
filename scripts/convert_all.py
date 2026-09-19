"""Convert the participant attachment bundle and print the Phase 4 summary."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings_from_env
from backend.app.pipeline.convert import convert_all, summary
from backend.app.pipeline.ingest import ingest


def main() -> None:
    settings = settings_from_env()
    ingest(settings)
    results = convert_all(settings)
    print("format       ok  degraded  failed")
    for extension, counts in sorted(summary(results).items()):
        print(f"{extension:<10} {counts['ok']:>2} {counts['degraded']:>9} {counts['failed']:>7}")


if __name__ == "__main__":
    main()
