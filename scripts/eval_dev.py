"""Evaluate persisted verdicts against a team-authored, evidence-noted dev set."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.submission import submission_rows


REVIEW_REASONS = frozenset({"wrong_doc_type", "missing_attachment", "unreadable", "missing_value"})


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
    exact = end_to_end = review_reason_correct = review_reason_total = 0
    for email_id, label in labels.items():
        if email_id not in rows or not isinstance(label, dict) or not isinstance(label.get("evidence"), str) or not label["evidence"].strip():
            raise ValueError(f"{email_id}: label needs an existing email and one-line evidence")
        actual_category = label.get("category")
        if actual_category not in categories:
            raise ValueError(f"{email_id}: invalid category")
        actual_status = label.get("status")
        if actual_status not in {"OK", "MISMATCH", "NEEDS_REVIEW"}:
            raise ValueError(f"{email_id}: invalid status")
        actual_reason = label.get("review_reason")
        if actual_status == "NEEDS_REVIEW":
            if actual_reason not in REVIEW_REASONS:
                raise ValueError(f"{email_id}: review labels need a valid review_reason")
        elif actual_reason not in (None, ""):
            raise ValueError(f"{email_id}: non-review labels cannot carry review_reason")
        else:
            actual_reason = None
        predicted = rows[email_id]
        matrix[actual_category][predicted["category"]] += 1
        actual_fields = set(label.get("defect_fields", []))
        predicted_fields = set(predicted["defect_fields"])
        for index, value in enumerate(_score(predicted_fields, actual_fields)): defect[index] += value
        actual_review = actual_status == "NEEDS_REVIEW"
        predicted_review = predicted["status"] == "NEEDS_REVIEW"
        escalation[0] += int(actual_review and predicted_review); escalation[1] += int(predicted_review and not actual_review); escalation[2] += int(actual_review and not predicted_review)
        if actual_review:
            review_reason_total += 1
            review_reason_correct += int(predicted.get("review_reason") == actual_reason)
        exact += int(predicted_fields == actual_fields)
        end_to_end += int(predicted["category"] == actual_category and predicted["status"] == actual_status and predicted.get("review_reason") == actual_reason and predicted_fields == actual_fields)
    per_class = {}
    for category in categories:
        tp = matrix[category][category]; fp = sum(matrix[actual][category] for actual in categories if actual != category); fn = sum(matrix[category][other] for other in categories if other != category)
        per_class[category] = _f1(tp, fp, fn)
    total = len(labels)
    return {"labels": total, "confusion_matrix": {key: dict(value) for key, value in matrix.items()}, "per_class_f1": per_class,
            "macro_f1": sum(per_class.values()) / len(per_class), "defect_f1": _f1(*defect), "exact_field_set_match": exact / total,
            "end_to_end_rate": end_to_end / total, "escalation_f1": _f1(*escalation),
            "review_reason_accuracy": review_reason_correct / review_reason_total if review_reason_total else None,
            "review_reason_labels": review_reason_total}


def show_misses(labels_path: Path, rows: dict[str, dict]) -> list[dict]:
    """Return evidence-bearing misses without changing the evaluation score."""
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    misses = []
    for email_id, label in labels.items():
        predicted = rows[email_id]
        expected = {
            "category": label.get("category"), "status": label.get("status"),
            "review_reason": label.get("review_reason"), "defect_fields": label.get("defect_fields", []),
        }
        actual = {
            "category": predicted.get("category"), "status": predicted.get("status"),
            "review_reason": predicted.get("review_reason"), "defect_fields": predicted.get("defect_fields", []),
        }
        if expected != actual:
            misses.append({"email_id": email_id, "expected": expected, "predicted": actual, "evidence": label.get("evidence")})
    return misses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=PROJECT_ROOT / "dev_labels" / "dev_labels.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dev_labels" / "eval_report.json")
    parser.add_argument("--show-misses", action="store_true", help="include label evidence and expected/predicted values for every miss")
    args = parser.parse_args()
    rows = submission_rows(settings_from_env().database_path)
    result = evaluate(args.labels, rows)
    if args.show_misses:
        result = {"metrics": result, "misses": show_misses(args.labels, rows)}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
