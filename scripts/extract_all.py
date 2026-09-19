"""Extract and normalize seven shipping fields from all converted documents."""
from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings_from_env
from backend.app.extract.pipeline import extract_all, write_reports
from backend.app.pipeline.convert import convert_all
from backend.app.pipeline.ingest import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gemini", action="store_true", help="allow configured Gemini alias discovery for unknown labels")
    args = parser.parse_args()
    settings = settings_from_env()
    ingest(settings)
    convert_all(settings)
    extract_all(settings, use_gemini=args.gemini)
    print(json.dumps(write_reports(settings), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
