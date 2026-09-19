"""Classify all indexed emails with rules, optionally allowing Gemini fallback."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.classify.pipeline import classify_all
from backend.app.config import settings_from_env
from backend.app.pipeline.ingest import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gemini", action="store_true", help="allow the configured Gemini fallback for uncertain mail")
    parser.add_argument("--force", action="store_true", help="rerun non-overridden classifications")
    args = parser.parse_args()
    settings = settings_from_env()
    ingest(settings)
    result = classify_all(settings, use_gemini=args.gemini, force=args.force)
    print(json.dumps({"categories": result.categories, "decisions": result.decisions, "skipped": result.skipped, "gemini_calls": result.gemini_calls}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
