from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.classify.pipeline import classify_all
from backend.app.compare import _ports_equal, compare_all, compare_email
from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database, initialize
from backend.app.extract.aliases import FIELDS
from backend.app.extract.pipeline import extract_all
from backend.app.main import create_app
from backend.app.pipeline.convert import convert_all
from backend.app.pipeline.ingest import ingest


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.settings = settings_from_env({"DATA_DIR": PROJECT_ROOT / "data", "DATABASE_PATH": root / "index.sqlite3", "DERIVED_DIR": root / "derived"})
        ingest(cls.settings, reset=True); convert_all(cls.settings); classify_all(cls.settings); extract_all(cls.settings); compare_all(cls.settings)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_known_mismatch_and_unreadable_review(self):
        mismatch = compare_email(self.settings, "email_031")
        self.assertEqual("MISMATCH", mismatch["status"])
        self.assertEqual(["container_count", "gross_weight_kg"], mismatch["defect_fields"])
        review = compare_email(self.settings, "email_512")
        self.assertEqual(("NEEDS_REVIEW", "unreadable"), (review["status"], review["review_reason"]))

    def test_api_returns_persisted_comparison_shape(self):
        app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": self.settings.database_path, "DERIVED_DIR": self.settings.derived_dir})
        response = app.test_client().get("/api/emails/email_031/comparison")
        self.assertEqual(200, response.status_code)
        self.assertIn("field_results", response.get_json())

    def test_api_can_sort_bl_comparisons_with_mismatches_first(self):
        app = create_app({"DATA_DIR": self.settings.data_dir, "DATABASE_PATH": self.settings.database_path, "DERIVED_DIR": self.settings.derived_dir})
        response = app.test_client().get("/api/emails?category=BL_COMPARISON&sort=mismatch_first&page_size=520")
        self.assertEqual(200, response.status_code)
        rank = {"MISMATCH": 0, "NEEDS_REVIEW": 1, "OK": 2, None: 3}
        self.assertEqual(sorted(rank[row["status"]] for row in response.get_json()), [rank[row["status"]] for row in response.get_json()])

    def test_port_codes_must_match_when_both_are_present(self):
        left = {"normalized": "NANTONG CHINA", "raw": "NANTONG, CHINA (CNNTG)"}
        right = {"normalized": "NANTONG CHINA", "raw": "NANTONG CHINA (CNSHA)"}
        self.assertFalse(_ports_equal(left, right))

    def test_recomputation_preserves_identical_result_timestamp(self):
        with database(self.settings.database_path) as connection:
            first = connection.execute("SELECT computed_at FROM comparisons WHERE email_id = 'email_031'").fetchone()[0]
        compare_email(self.settings, "email_031")
        with database(self.settings.database_path) as connection:
            second = connection.execute("SELECT computed_at FROM comparisons WHERE email_id = 'email_031'").fetchone()[0]
        self.assertEqual(first, second)

    def test_appendix_d_status_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_from_env({"DATABASE_PATH": Path(directory) / "status.sqlite3"})
            initialize(settings.database_path)

            def make_case(email_id, *, category="BL_COMPARISON", documents=2, failed=False, rows=True, blank=False, low_confidence=False):
                with database(settings.database_path) as connection:
                    connection.execute("INSERT INTO emails (email_id, from_addr, subject, body, category) VALUES (?, 'a@b.test', '', '', ?)", (email_id, category))
                    for role in ("SI", "BL")[:documents]:
                        doc_id = f"{email_id}_{role}"
                        connection.execute("INSERT INTO documents (doc_id, email_id, path, ext, size, sha256, role_detected, convert_status) VALUES (?, ?, ?, '.txt', 1, 'x', ?, ?)", (doc_id, email_id, f"attachments/{doc_id}.txt", role, "failed" if failed else "ok"))
                        if rows:
                            values = []
                            for field in FIELDS:
                                status = "blank" if blank and field == "shipper" else "found"
                                values.append((doc_id, field, "VALUE", "VALUE", 1, 0.5 if low_confidence and field == "shipper" else 1.0, status))
                            connection.executemany("INSERT INTO extractions (doc_id, field, raw, normalized, line_no, confidence, status) VALUES (?, ?, ?, ?, ?, ?, ?)", values)

            make_case("not-comparison", category="GENERAL", documents=0)
            make_case("missing-attachment", documents=1)
            make_case("unreadable", failed=True)
            make_case("wrong-document-type", rows=False)
            make_case("missing-value", blank=True)
            make_case("low-confidence", low_confidence=True)
            expected = {
                "not-comparison": ("OK", None),
                "missing-attachment": ("NEEDS_REVIEW", "missing_attachment"),
                "unreadable": ("NEEDS_REVIEW", "unreadable"),
                "wrong-document-type": ("NEEDS_REVIEW", "wrong_doc_type"),
                "missing-value": ("NEEDS_REVIEW", "missing_value"),
                "low-confidence": ("NEEDS_REVIEW", "unreadable"),
            }
            for email_id, verdict in expected.items():
                result = compare_email(settings, email_id)
                self.assertEqual(verdict, (result["status"], result["review_reason"]))


if __name__ == "__main__": unittest.main()
