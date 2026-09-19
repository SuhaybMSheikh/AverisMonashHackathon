from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database
from backend.app.main import create_app
from backend.app.pipeline.convert import convert_all, validate_canonical
from backend.app.pipeline.ingest import ingest


GOLDEN_SHA256 = {
    "email_004_SI": "9999bc211a85fbf68de6ded4c68b0b4a5bc7ea16cc27aaba23b736332c091c1a",
    "email_004_BL": "083fec3ad529d756c3d309092330f8fea395174e1552efcaa7ad571755e7b05c",
    "email_005_SI": "41faae418cbfb642de08fdb8baacc918d934042bda670e40f9686553a6f5bbab",
    "email_005_BL": "e07d46cc3887cd454800e32e6865929f8fcd666b069b3d2f5c6262a050557d3c",
    "email_055_SI": "12e728dafdd7fe390171d62a81a1fd35efad42f9e290392d0ae6ff1108841867",
    "email_055_BL": "86af4b9b10766d85be918436f7c9a9ac0633db8a99735527279ce0cb8587ad62",
    "email_097_BL": "d9b6cc2a8d730435abc1d943da232fcb0ae8d289db2e9c2bcbf4988dc500ec5e",
    "email_499_SI": "1019c47cf2bf3e4b6ce3173a6cd0d25c7ef76ea0d4fa91427697ed6435fc4a31",
    "email_499_BL": "41a6087190478e31e14223e69c93b79c85d188e48652c7a1b3641ac7b95cef15",
}


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.settings = settings_from_env(
            {
                "DATA_DIR": PROJECT_ROOT / "data",
                "DATABASE_PATH": Path(cls.temporary_directory.name) / "index.sqlite3",
                "DERIVED_DIR": Path(cls.temporary_directory.name) / "derived",
            }
        )
        ingest(cls.settings, reset=True)
        cls.results = convert_all(cls.settings)
        cls.by_id = {result.doc_id: result for result in cls.results}

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def test_all_attachments_receive_text_and_metadata_sidecars(self):
        self.assertEqual(250, len(self.results))
        for result in self.results:
            text_path = self.settings.derived_dir / "text" / f"{result.doc_id}.txt"
            meta_path = self.settings.derived_dir / "meta" / f"{result.doc_id}.json"
            self.assertTrue(text_path.is_file(), result.doc_id)
            self.assertTrue(meta_path.is_file(), result.doc_id)
            self.assertEqual(result.metadata, json.loads(meta_path.read_text(encoding="utf-8")))
            if result.metadata["status"] != "failed":
                wrong_type = any(item.startswith("wrong_doc_type_candidate") for item in result.metadata["warnings"])
                self.assertEqual([], validate_canonical(result.text, require_shipping_fields=not wrong_type), result.doc_id)

    def test_readable_formats_are_ok_and_known_pdf_failures_are_explicit(self):
        statuses = Counter((Path(result.metadata["source"]).suffix, result.metadata["status"]) for result in self.results)
        self.assertEqual(192, statuses[(".txt", "ok")])
        self.assertEqual(22, statuses[(".xlsx", "ok")])
        self.assertEqual(8, statuses[(".docx", "ok")])
        self.assertEqual(20, statuses[(".pdf", "ok")])
        self.assertEqual(8, statuses[(".pdf", "failed")])

        for document_id in ("email_511_BL", "email_515_BL"):
            metadata = self.by_id[document_id].metadata
            self.assertEqual("failed", metadata["status"])
            self.assertIn("corrupt_pdf", metadata["warnings"])

        for document_id in ("email_512_BL", "email_512_SI", "email_513_BL", "email_513_SI", "email_514_BL", "email_514_SI"):
            metadata = self.by_id[document_id].metadata
            self.assertEqual("failed", metadata["status"])
            self.assertIn("scan_readers_unavailable", metadata["warnings"])
            self.assertEqual(sorted(metadata["uncertain_fields"]), metadata["uncertain_fields"])

    def test_golden_outputs_are_byte_stable_for_each_readable_format(self):
        for document_id, expected_hash in GOLDEN_SHA256.items():
            output = self.by_id[document_id].text.encode("utf-8")
            self.assertEqual(expected_hash, hashlib.sha256(output).hexdigest(), document_id)
            self.assertEqual(output, convert_all(self.settings, {document_id})[0].text.encode("utf-8"), document_id)

    def test_preview_uses_canonical_text_after_conversion(self):
        app = create_app(
            {
                "DATA_DIR": self.settings.data_dir,
                "DATABASE_PATH": self.settings.database_path,
                "DERIVED_DIR": self.settings.derived_dir,
            }
        )
        app.testing = True
        preview = app.test_client().get("/api/documents/email_055_BL/preview")
        self.assertEqual(200, preview.status_code)
        payload = preview.get_json()
        self.assertEqual("canonical_text", payload["metadata"]["formatted_source"])
        self.assertTrue(any(field["label"] == "B/L NO.(提单号)" for field in payload["fields"]))

        canonical = app.test_client().get("/api/documents/email_055_BL/text")
        self.assertEqual(200, canonical.status_code)
        self.assertTrue(canonical.get_data(as_text=True).startswith("BILL OF LADING (DRAFT)"))


if __name__ == "__main__":
    unittest.main()
