"""Evaluate persisted verdicts against a team-authored, evidence-noted dev set."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.submission import submission_rows


def _score(predicted: set[str], actual: set[str]) -> tuple[int, int, int]:
    return len(predicted & actual), len(predicted - actual), len(actual - predicted)


def _f1(tp: int, fp: int, fn: int) -> float:
    return 0.0 if not 2 * tp + fp + fn else 2 * tp / (2 * tp + fp + fn)


def evaluate(labels_path: Path, rows: dict[str, dict]) -> dict:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    if not isinstance(labels, dict) or not 40 <= len(labels) <= 60:
        raise ValueError("dev_labels.json must contain 40 to 60 reviewed emails")
    categories = sorted({row["category"] for row in rows.values()})
    matrix = {actual: Counter() for actual in categories}
    defect = [0, 0, 0]
    escalation = [0, 0, 0]
    exact = end_to_end = 0
    for email_id, label in labels.items():
        if email_id not in rows or not isinstance(label, dict) or not isinstance(label.get("evidence"), str) or not label["evidence"].strip():
            raise ValueError(f"{email_id}: label needs an existing email and one-line evidence")
        actual_category = label.get("category")
        if actual_category not in categories:
            raise ValueError(f"{email_id}: invalid category")
        predicted = rows[email_id]
        matrix[actual_category][predicted["category"]] += 1
        actual_fields = set(label.get("defect_fields", []))
        predicted_fields = set(predicted["defect_fields"])
        for index, value in enumerate(_score(predicted_fields, actual_fields)): defect[index] += value
        actual_review = label.get("status") == "NEEDS_REVIEW"
        predicted_review = predicted["status"] == "NEEDS_REVIEW"
        escalation[0] += int(actual_review and predicted_review); escalation[1] += int(predicted_review and not actual_review); escalation[2] += int(actual_review and not predicted_review)
        exact += int(predicted_fields == actual_fields)
        end_to_end += int(predicted["category"] == actual_category and predicted["status"] == label.get("status") and predicted_fields == actual_fields)
    per_class = {}
    for category in categories:
        tp = matrix[category][category]; fp = sum(matrix[actual][category] for actual in categories if actual != category); fn = sum(matrix[category][other] for other in categories if other != category)
        per_class[category] = _f1(tp, fp, fn)
    total = len(labels)
    return {"labels": total, "confusion_matrix": {key: dict(value) for key, value in matrix.items()}, "per_class_f1": per_class,
            "macro_f1": sum(per_class.values()) / len(per_class), "defect_f1": _f1(*defect), "exact_field_set_match": exact / total,
            "end_to_end_rate": end_to_end / total, "escalation_f1": _f1(*escalation)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=PROJECT_ROOT / "dev_labels" / "dev_labels.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dev_labels" / "eval_report.json")
    args = parser.parse_args()
    result = evaluate(args.labels, submission_rows(settings_from_env().database_path))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
