from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import scripts.build_blind_label_kit as kit
from scripts.compare_labels import disagreements
from scripts.eval_dev import evaluate


class BlindLabelKitTests(unittest.TestCase):
    def test_fixed_seed_kit_is_blind_and_has_required_sizes(self):
        groups = kit.select_groups()
        self.assertEqual(
            {"comparison_txt": 5, "comparison_xlsx": 3, "comparison_mixed": 3,
             "comparison_text_pdf": 3, "comparison_scan": 2, "comparison_corrupt_pdf": 2,
             "comparison_missing_attachment": 2, "trap_no_attachment_draft": 2,
             "trap_misleading_subject": 3, "other_si_request": 4, "other_invoice": 4,
             "other_general": 3, "other_spam": 4},
            {name: len(ids) for name, ids in groups.items()},
        )
        selected, paired = kit.select_ids()
        self.assertEqual(40, len(selected))
        self.assertEqual(20, len(paired))
        self.assertEqual(40, len(set(selected)))
        with tempfile.TemporaryDirectory() as directory:
            original_sheet, original_todo = kit.REVIEW_SHEET, kit.TODO_FILE
            try:
                kit.REVIEW_SHEET = Path(directory) / "review_sheet.md"
                kit.TODO_FILE = Path(directory) / "dev_labels.todo.json"
                kit.write_kit()
                sheet = kit.REVIEW_SHEET.read_text(encoding="utf-8")
                todo = json.loads(kit.TODO_FILE.read_text(encoding="utf-8"))
            finally:
                kit.REVIEW_SHEET, kit.TODO_FILE = original_sheet, original_todo
        self.assertEqual(40, sheet.count("## Email "))
        self.assertEqual(20, sheet.count("Shipping instruction — canonical text"))
        self.assertEqual(set(selected), set(todo))
        self.assertTrue(all(label == {"category": "", "status": "", "review_reason": "", "defect_fields": [], "evidence": ""} for label in todo.values()))

    def test_review_reason_is_evaluated_and_label_disagreements_ignore_evidence(self):
        rows = {
            f"email_{index:03d}": {"category": "GENERAL", "status": "OK", "review_reason": None, "defect_fields": []}
            for index in range(1, 41)
        }
        rows["email_001"] = {"category": "GENERAL", "status": "NEEDS_REVIEW", "review_reason": "unreadable", "defect_fields": []}
        labels = {
            email_id: {"category": "GENERAL", "status": "OK", "review_reason": "", "defect_fields": [], "evidence": "source note"}
            for email_id in rows
        }
        labels["email_001"] = {"category": "GENERAL", "status": "NEEDS_REVIEW", "review_reason": "unreadable", "defect_fields": [], "evidence": "source note"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labels.json"
            path.write_text(json.dumps(labels), encoding="utf-8")
            report = evaluate(path, rows)
        self.assertEqual(1, report["review_reason_labels"])
        self.assertEqual(1.0, report["review_reason_accuracy"])
        other = {email_id: {**label, "evidence": "another note"} for email_id, label in labels.items()}
        other["email_001"] = {**other["email_001"], "review_reason": "missing_value"}
        self.assertEqual(["email_001"], [item["email_id"] for item in disagreements(labels, other)])


if __name__ == "__main__":
    unittest.main()
