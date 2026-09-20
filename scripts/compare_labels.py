"""Print completed-label records where two independent labelers disagree."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = ("category", "status", "review_reason", "defect_fields")


def _load(path: Path) -> dict[str, dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(email_id, str) and isinstance(label, dict) for email_id, label in value.items()):
        raise ValueError(f"{path}: expected an object keyed by email ID")
    return value


def _value(label: dict, field: str):
    value = label.get(field)
    return sorted(value) if field == "defect_fields" and isinstance(value, list) else value


def disagreements(first: dict[str, dict], second: dict[str, dict]) -> list[dict]:
    """Compare label fields only; free-text evidence is intentionally not scored."""
    result = []
    for email_id in sorted(set(first) | set(second)):
        if email_id not in first or email_id not in second:
            result.append({"email_id": email_id, "missing_from": "first" if email_id not in first else "second"})
            continue
        different = {
            field: {"first": _value(first[email_id], field), "second": _value(second[email_id], field)}
            for field in FIELDS
            if _value(first[email_id], field) != _value(second[email_id], field)
        }
        if different:
            result.append({"email_id": email_id, "differences": different})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path, help="first labeler JSON file")
    parser.add_argument("second", type=Path, help="second labeler JSON file")
    args = parser.parse_args()
    result = disagreements(_load(args.first), _load(args.second))
    if not result:
        print("No disagreements.")
        return
    for item in result:
        print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    raise SystemExit(1)


if __name__ == "__main__":
    main()
