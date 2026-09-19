"""Evaluate persisted classifications against the team's hand-labeled dev set."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.classify.rules import CATEGORIES
from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database


def report(labels_path: Path, database_path: Path) -> str:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    with database(database_path) as connection:
        predicted = {row["email_id"]: row["category"] for row in connection.execute("SELECT email_id, category FROM emails")}
    matrix = {actual: Counter() for actual in sorted(CATEGORIES)}
    for email_id, actual in labels.items():
        if actual not in CATEGORIES or email_id not in predicted:
            raise ValueError(f"invalid dev label or missing email: {email_id}")
        matrix[actual][predicted[email_id]] += 1
    ordered = sorted(CATEGORIES)
    lines = ["Confusion matrix (rows=actual, columns=predicted)", "actual\\predicted " + " ".join(ordered)]
    for actual in ordered:
        lines.append(actual + " " + " ".join(str(matrix[actual][predicted_class]) for predicted_class in ordered))
    lines.append("\nPer-class F1")
    for category in ordered:
        true_positive = matrix[category][category]
        false_positive = sum(matrix[actual][category] for actual in CATEGORIES if actual != category)
        false_negative = sum(matrix[category][predicted_class] for predicted_class in CATEGORIES if predicted_class != category)
        denominator = 2 * true_positive + false_positive + false_negative
        lines.append(f"{category}: {2 * true_positive / denominator:.3f}" if denominator else f"{category}: n/a")
    return "\n".join(lines)


if __name__ == "__main__":
    settings = settings_from_env()
    print(report(PROJECT_ROOT / "dev_labels" / "classification_dev_set.json", settings.database_path))
