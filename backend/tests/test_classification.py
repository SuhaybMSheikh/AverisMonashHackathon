from __future__ import annotations

import tempfile
import json
import unittest
from pathlib import Path

from backend.app.classify.pipeline import classify_all
from backend.app.classify.features import EmailFeatures
from backend.app.classify.rules import classify
from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database
from backend.app.main import create_app
from backend.app.pipeline.convert import convert_all
from backend.app.pipeline.ingest import ingest
from backend.app.submission import submission_rows, validate_submission
from scripts.evaluate_classification import report
from scripts.eval_dev import evaluate, show_misses


class ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(cls.temporary_directory.name)
        cls.settings = settings_from_env({"DATA_DIR": PROJECT_ROOT / "data", "DATABASE_PATH": root / "index.sqlite3", "DERIVED_DIR": root / "derived"})
        ingest(cls.settings, reset=True)
        convert_all(cls.settings)
        cls.first = classify_all(cls.settings)

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def test_every_email_is_persisted_in_one_of_the_five_categories(self):
        self.assertEqual(0, self.first.gemini_calls)
        with database(self.settings.database_path) as connection:
            rows = connection.execute("SELECT email_id, category, decided_by FROM emails").fetchall()
        self.assertEqual(520, len(rows))
        self.assertNotIn("UNCLASSIFIED", {row["category"] for row in rows})
        self.assertEqual({"rule"}, {row["decided_by"] for row in rows})

    def test_documented_known_traps_are_rules(self):
        with database(self.settings.database_path) as connection:
            rows = {row["email_id"]: row for row in connection.execute("SELECT email_id, category, decided_by, category_reasons FROM emails WHERE email_id IN ('email_003', 'email_012', 'email_021')")}
        self.assertEqual("BL_COMPARISON", rows["email_003"]["category"])
        self.assertIn("draft_bl_request_without_attachment", rows["email_003"]["category_reasons"])
        self.assertEqual("GENERAL", rows["email_012"]["category"])
        self.assertEqual("GENERAL", rows["email_021"]["category"])
        self.assertEqual({"rule"}, {row["decided_by"] for row in rows.values()})

    def test_general_invoice_and_spam_multi_signal_rules(self):
        def decision(body):
            return classify(EmailFeatures("test", "", body, "sender@example.test", "example.test", ()))
        self.assertEqual("INVOICE_QUERY", decision("Please cancel invoice 5250070303 and reverse the PGI.").category)
        self.assertEqual("INVOICE_QUERY", decision("Please confirm detention charges before payment.").category)
        self.assertEqual("SPAM", decision("Pay customs payment at track-parcel.info within 24 hours.").category)
        self.assertEqual("SPAM", decision("Reply with your bank details for this USD 4.5 million proposal.").category)
        self.assertEqual("SPAM", decision("Limited time promotion: get 90% off, buy now.").category)

    def test_rerun_does_not_call_gemini_or_change_categories(self):
        rerun = classify_all(self.settings, use_gemini=True)
        self.assertEqual(0, rerun.gemini_calls)
        self.assertEqual(520, rerun.skipped)

    def test_api_exposes_real_category_counts_and_confidence(self):
        app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": self.settings.database_path, "DERIVED_DIR": self.settings.derived_dir})
        client = app.test_client()
        counts = client.get("/api/emails/counts").get_json()
        self.assertEqual(520, counts["all"])
        self.assertGreater(counts["categories"]["BL_COMPARISON"], 0)
        item = client.get("/api/emails?category=BL_COMPARISON&page_size=1").get_json()[0]
        self.assertIn("category_conf", item)
        self.assertIn("decided_by", item)

    def test_category_override_and_si_body_fields_are_exposed(self):
        app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": self.settings.database_path, "DERIVED_DIR": self.settings.derived_dir})
        client = app.test_client()
        response = client.post("/api/emails/email_003/category", json={"category": "SPAM"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("SPAM", client.get("/api/emails/email_003").get_json()["category"])
        self.assertEqual("SPAM", client.get("/api/emails?category=SPAM&page_size=520").get_json()[-1]["category"])
        client.post("/api/emails/email_003/category", json={"category": "GENERAL"})
        si_email = client.get("/api/emails?category=SI_REQUEST&page_size=1").get_json()[0]
        fields = client.get(f"/api/emails/{si_email['email_id']}/body-fields")
        self.assertEqual(200, fields.status_code)
        self.assertEqual(7, len(fields.get_json()))

    def test_submission_rows_use_category_override(self):
        app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": self.settings.database_path, "DERIVED_DIR": self.settings.derived_dir})
        client = app.test_client()
        client.post("/api/emails/email_003/category", json={"category": "SPAM"})
        self.assertEqual("SPAM", submission_rows(self.settings.database_path)["email_003"]["category"])
        client.post("/api/emails/email_003/category", json={"category": "GENERAL"})

    def test_submission_rows_match_the_published_schema(self):
        rows = submission_rows(self.settings.database_path, include_decided_by=True)
        validate_submission(rows, PROJECT_ROOT / "data" / "sample_submission.json")
        self.assertEqual(520, len(rows))

    def test_dev_evaluator_reports_all_required_metrics(self):
        rows = {f"email_{index:03d}": {"category": "GENERAL", "status": "OK", "defect_fields": []} for index in range(1, 41)}
        labels = {email_id: {"category": "GENERAL", "status": "OK", "defect_fields": [], "evidence": "Reviewed message and source evidence."} for email_id in rows}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dev_labels.json"
            path.write_text(json.dumps(labels), encoding="utf-8")
            result = evaluate(path, rows)
        self.assertEqual(40, result["labels"])
        self.assertEqual({"confusion_matrix", "per_class_f1", "macro_f1", "defect_f1", "exact_field_set_match", "end_to_end_rate", "escalation_f1", "review_reason_accuracy", "review_reason_labels", "labels"}, set(result))

    def test_dev_evaluator_show_misses_includes_evidence(self):
        rows = {"email_001": {"category": "GENERAL", "status": "OK", "review_reason": None, "defect_fields": []}}
        labels = {"email_001": {"category": "SPAM", "status": "OK", "review_reason": None, "defect_fields": [], "evidence": "Positive spam evidence."}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dev_labels.json"
            path.write_text(json.dumps(labels), encoding="utf-8")
            misses = show_misses(path, rows)
        self.assertEqual([{"email_id": "email_001", "expected": {"category": "SPAM", "status": "OK", "review_reason": None, "defect_fields": []}, "predicted": {"category": "GENERAL", "status": "OK", "review_reason": None, "defect_fields": []}, "evidence": "Positive spam evidence."}], misses)

    def test_team_dev_set_report_is_available(self):
        result = report(PROJECT_ROOT / "dev_labels" / "classification_dev_set.json", self.settings.database_path)
        self.assertIn("Confusion matrix", result)
        self.assertIn("BL_COMPARISON", result)


if __name__ == "__main__":
    unittest.main()
