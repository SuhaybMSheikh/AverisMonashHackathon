from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database
from backend.app.main import create_app
from backend.app.pipeline.ingest import attachment_path, ingest


class DataLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.settings = settings_from_env(
            {
                "DATA_DIR": PROJECT_ROOT / "data",
                "DATABASE_PATH": Path(cls.temporary_directory.name) / "index.sqlite3",
            }
        )
        cls.result = ingest(cls.settings, reset=True)
        cls.app = create_app(
            {"DATA_DIR": cls.settings.data_dir, "DATABASE_PATH": cls.settings.database_path}
        )
        cls.app.testing = True
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def test_ingest_is_complete_and_idempotent(self):
        self.assertEqual(520, self.result.emails)
        self.assertEqual(250, self.result.documents)
        repeated = ingest(self.settings)
        self.assertEqual(self.result, repeated)
        with database(self.settings.database_path) as connection:
            self.assertEqual(520, connection.execute("SELECT COUNT(*) FROM emails").fetchone()[0])
            self.assertEqual(250, connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            self.assertEqual(
                520,
                connection.execute("SELECT COUNT(*) FROM emails WHERE category = 'UNCLASSIFIED'").fetchone()[0],
            )

    def test_list_api_defaults_to_all_emails_and_supports_search_and_pagination(self):
        response = self.client.get("/api/emails")
        self.assertEqual(200, response.status_code)
        self.assertEqual(520, len(response.get_json()))
        self.assertEqual("520", response.headers["X-Total-Count"])

        response = self.client.get("/api/emails?q=5ALT-01226&page_size=1")
        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(1, len(payload))
        self.assertEqual("email_004", payload[0]["email_id"])
        self.assertEqual("UNCLASSIFIED", payload[0]["category"])
        self.assertIn(".txt", payload[0]["formats"])

        sender_matches = self.client.get("/api/emails?q=docs@vitalsolutions.sg").get_json()
        self.assertIn("email_004", [item["email_id"] for item in sender_matches])
        body_matches = self.client.get("/api/emails?q=COATED+IVORY+BOARD").get_json()
        self.assertIn("email_004", [item["email_id"] for item in body_matches])
        self.assertEqual(520, len(self.client.get("/api/emails?category=UNCLASSIFIED").get_json()))
        self.assertEqual([], self.client.get("/api/emails?status=OK").get_json())

    def test_document_metadata_and_original_are_correct(self):
        response = self.client.get("/api/emails/email_004/documents")
        self.assertEqual(200, response.status_code)
        documents = response.get_json()
        self.assertEqual(2, len(documents))
        self.assertEqual({".txt"}, {document["ext"] for document in documents})
        self.assertEqual({"SI", "BL"}, {document["role_hint"] for document in documents})

        document = next(item for item in documents if item["doc_id"] == "email_004_SI")
        source = PROJECT_ROOT / "data" / document["path"]
        self.assertEqual("attachments/email_004_SI.txt", document["path"])
        self.assertEqual(source.stat().st_size, document["size"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), document["sha256"])

        original = self.client.get(f"/api/documents/{document['doc_id']}/original")
        self.assertEqual(200, original.status_code)
        self.assertEqual(source.read_bytes(), original.data)
        original.close()

    def test_path_traversal_is_not_served(self):
        self.assertEqual(404, self.client.get("/api/documents/..%2Fsecret/original").status_code)
        with self.assertRaises(FileNotFoundError):
            attachment_path(self.settings.data_dir, "attachments/../secret")

    def test_health_and_single_email_endpoints(self):
        health = self.client.get("/api/health")
        self.assertEqual(200, health.status_code)
        self.assertEqual({"status": "healthy", "database": "ready", "emails": 520, "documents": 250}, health.get_json())

        email = self.client.get("/api/emails/email_004")
        self.assertEqual(200, email.status_code)
        self.assertEqual("email_004", email.get_json()["email_id"])
        self.assertEqual(2, len(email.get_json()["documents"]))


if __name__ == "__main__":
    unittest.main()
