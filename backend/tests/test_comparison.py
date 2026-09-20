from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.classify.pipeline import classify_all
from backend.app.compare import _diff_segments, _party_comparison, _ports_equal, compare_all, compare_email
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

    def test_ports_compare_names_and_ignore_unlocodes(self):
        left = {"normalized": "NANTONG CHINA", "raw": "NANTONG, CHINA (CNNTG)"}
        right = {"normalized": "NANTONG CHINA", "raw": "NANTONG CHINA (CNSHA)"}
        self.assertTrue(_ports_equal(left, right))
        self.assertFalse(_ports_equal(left, {"normalized": "SHANGHAI CHINA", "raw": "SHANGHAI, CHINA (CNSHA)"}))

    def test_party_name_and_address_policy(self):
        left = {"raw": "EXAMPLE TRADING CO\n12 HARBOUR ROAD", "normalized": "EXAMPLE TRADING CO 12 HARBOUR ROAD"}
        right = {"raw": "EXAMPLE TRADING CO", "normalized": "EXAMPLE TRADING CO"}
        self.assertEqual((True, "SI has an additional address; normalized party names match."), _party_comparison(left, right))
        self.assertEqual((False, None), _party_comparison(left, {"raw": "EXAMPLE TRADING CO\n99 RIVER ROAD", "normalized": "EXAMPLE TRADING CO 99 RIVER ROAD"}))
        self.assertEqual((False, None), _party_comparison(left, {"raw": "OTHER TRADING CO\n12 HARBOUR ROAD", "normalized": "OTHER TRADING CO 12 HARBOUR ROAD"}))

    def test_token_diff_keeps_unchanged_numeric_suffixes(self):
        self.assertEqual(
            [{"text": "4", "changed": False}, {"text": "1", "changed": True}, {"text": ",326", "changed": False}],
            _diff_segments("40,326", "41,326"),
        )

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

            def make_case(email_id, *, category="BL_COMPARISON", category_reasons=None, documents=2, failed=False, rows=True, blank=False, low_confidence=False):
                with database(settings.database_path) as connection:
                    connection.execute("INSERT INTO emails (email_id, from_addr, subject, body, category, category_reasons) VALUES (?, 'a@b.test', '', '', ?, ?)", (email_id, category, category_reasons))
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
            make_case("draft-request", documents=0, category_reasons=json.dumps(["draft_bl_request_without_attachment"]))
            make_case("missing-attachment", documents=1)
            make_case("unreadable", failed=True)
            make_case("wrong-document-type", rows=False)
            make_case("missing-value", blank=True)
            make_case("low-confidence", low_confidence=True)
            expected = {
                "not-comparison": ("OK", None),
                "draft-request": ("OK", None),
                "missing-attachment": ("NEEDS_REVIEW", "missing_attachment"),
                "unreadable": ("NEEDS_REVIEW", "unreadable"),
                "wrong-document-type": ("NEEDS_REVIEW", "wrong_doc_type"),
                "missing-value": ("NEEDS_REVIEW", "missing_value"),
                "low-confidence": ("NEEDS_REVIEW", "unreadable"),
            }
            for email_id, verdict in expected.items():
                result = compare_email(settings, email_id)
                self.assertEqual(verdict, (result["status"], result["review_reason"]))

    def test_review_api_overlays_value_without_mutating_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = settings_from_env({"DATABASE_PATH": Path(directory) / "review.sqlite3", "DATA_DIR": self.settings.data_dir, "DERIVED_DIR": Path(directory) / "derived"})
            initialize(settings.database_path)
            with database(settings.database_path) as connection:
                connection.execute("INSERT INTO emails (email_id, from_addr, subject, body, category) VALUES ('review-case', 'sender@example.test', 'Subject', '', 'BL_COMPARISON')")
                for role in ("SI", "BL"):
                    doc_id = f"review-case_{role}"
                    connection.execute("INSERT INTO documents (doc_id, email_id, path, ext, size, sha256, role_detected, convert_status) VALUES (?, 'review-case', ?, '.txt', 1, 'hash', ?, 'ok')", (doc_id, f"attachments/{doc_id}.txt", role))
                    for field in FIELDS:
                        raw, normalized, status = ("VALUE", "VALUE", "found")
                        if role == "BL" and field == "shipper":
                            raw, normalized, status = (None, None, "blank")
                        connection.execute("INSERT INTO extractions (doc_id, field, raw, normalized, line_no, confidence, status) VALUES (?, ?, ?, ?, 1, 1, ?)", (doc_id, field, raw, normalized, status))
            initial = compare_email(settings, "review-case")
            self.assertEqual("NEEDS_REVIEW", initial["status"])
            self.assertEqual("BL", initial["field_results"][0]["review_side"])
            app = create_app({"DATABASE_PATH": settings.database_path, "DATA_DIR": settings.data_dir, "DERIVED_DIR": settings.derived_dir})
            client = app.test_client()
            queue = client.get("/api/review-queue")
            self.assertEqual(["review-case"], [item["email_id"] for item in queue.get_json()])
            response = client.post("/api/emails/review-case/review", json={"field": "shipper", "doc_role": "BL", "value": "VALUE", "reviewer": "Ava", "note": "Confirmed against source", "disposition": "confirmed"})
            self.assertEqual(200, response.status_code)
            self.assertEqual("OK", response.get_json()["status"])
            with database(settings.database_path) as connection:
                original = connection.execute("SELECT raw, status FROM extractions WHERE doc_id = 'review-case_BL' AND field = 'shipper'").fetchone()
                self.assertEqual((None, "blank"), (original["raw"], original["status"]))
            comparison = client.get("/api/emails/review-case/comparison").get_json()
            self.assertEqual("VALUE", comparison["reviews"][-1]["value"])
            self.assertTrue(comparison["field_results"][0]["bl_reviewed"])
            self.assertEqual([], client.get("/api/review-queue").get_json())


if __name__ == "__main__": unittest.main()
