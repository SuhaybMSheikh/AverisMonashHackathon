from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database
from backend.app.main import create_app
from backend.app.pipeline.ingest import ingest
from backend.app.pipeline.convert import convert_all
from backend.app.extract.pipeline import extract_all
from backend.app.compare import compare_email
from backend.app.reliability import export_snapshot, record_stage, restore_snapshot
from backend.app.classify import gemini
from backend.app.classify.features import EmailFeatures


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = settings_from_env({"DATA_DIR": PROJECT_ROOT / "data", "DATABASE_PATH": root / "state.sqlite3", "DERIVED_DIR": root / "derived"})
        ingest(self.settings, reset=True)
        self.app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": self.settings.database_path, "DERIVED_DIR": self.settings.derived_dir})
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_failures_are_visible_and_snapshot_round_trips(self):
        record_stage(self.settings, ["email_004"], "convert", "failed", error="unreadable: corrupt_pdf", duration_ms=4)
        runs = self.client.get("/api/runs?failed=1")
        self.assertEqual(200, runs.status_code)
        self.assertEqual("email_004", runs.get_json()[0]["email_id"])
        self.assertEqual("unreadable: corrupt_pdf", runs.get_json()[0]["error"])
        snapshot = export_snapshot(self.settings)
        with database(self.settings.database_path) as connection:
            connection.execute("DELETE FROM stage_runs")
        restore_snapshot(self.settings, snapshot)
        self.assertEqual("failed", self.client.get("/api/runs?failed=1").get_json()[0]["state"])

    def test_retry_endpoint_rejects_unknown_email(self):
        self.assertEqual(404, self.client.post("/api/emails/no_such_email/retry", json={}).status_code)

    def test_demo_mode_loads_snapshot_without_pipeline_work(self):
        snapshot = export_snapshot(self.settings)
        demo_database = Path(self.temp.name) / "demo.sqlite3"
        with patch.dict(os.environ, {"DEMO_MODE": "1", "RESULTS_SNAPSHOT": str(snapshot)}, clear=False):
            demo_app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": demo_database, "DERIVED_DIR": self.settings.derived_dir})
            health = demo_app.test_client().get("/api/health").get_json()
        self.assertTrue(health["demo_mode"])
        self.assertEqual(520, health["emails"])

    def test_missing_key_and_malformed_gemini_response_are_failures(self):
        features = EmailFeatures("llm-case", "uncertain", "unclassified text", "sender@example.com", "example.com", ())
        with patch.dict("os.environ", {"GEMINI_ENABLED": "false"}, clear=False):
            self.assertIsNone(gemini.classify(features, self.settings.derived_dir))
            self.assertEqual("gemini_disabled", gemini.failure_for("llm-case"))

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self): return b'{"candidates":[{"content":{"parts":[{"text":"{bad json"}]}}]}'

        with patch.dict("os.environ", {"GEMINI_ENABLED": "true", "GEMINI_API_KEY": "test-key"}, clear=False), patch("urllib.request.urlopen", return_value=Response()):
            self.assertIsNone(gemini.classify(features, self.settings.derived_dir))
            self.assertEqual("gemini_invalid_schema", gemini.failure_for("llm-case"))

    def test_deleted_attachment_becomes_missing_attachment_review_reason(self):
        class MissingInbox:
            def __init__(self, _): pass
            def emails(self):
                return [{"email_id": "missing-file", "from": "x@example.com", "subject": "missing", "body": "", "attachments": ["attachments/missing-file_SI.txt"]}]
        with patch("backend.app.pipeline.ingest.Inbox", MissingInbox):
            ingest(self.settings, reset=True)
        with database(self.settings.database_path) as connection:
            connection.execute("UPDATE emails SET category = 'BL_COMPARISON' WHERE email_id = 'missing-file'")
        convert_all(self.settings)
        extract_all(self.settings)
        comparison = compare_email(self.settings, "missing-file")
        self.assertEqual(("NEEDS_REVIEW", "missing_attachment"), (comparison["status"], comparison["review_reason"]))


if __name__ == "__main__":
    unittest.main()
