from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database
from backend.app.extract.aliases import resolve
from backend.app.extract.parser import parse
from backend.app.extract.pipeline import FIELDS, extract_all, extract_text, write_reports
from backend.app.normalize import normalize
from backend.app.pipeline.convert import convert_all
from backend.app.pipeline.ingest import ingest


class ExtractionUnitTests(unittest.TestCase):
    def test_parser_keeps_continuation_evidence(self):
        entries = parse("SHIPPING INSTRUCTION\n====\nShipper: ACME SDN. BHD.\n  Kuala Lumpur, Malaysia\nPOD: Karachi\n")
        self.assertEqual(2, len(entries))
        self.assertEqual("Shipper", entries[0].label)
        self.assertEqual("ACME SDN. BHD.\nKuala Lumpur, Malaysia", entries[0].raw)
        self.assertEqual(3, entries[0].line_no)

    def test_parser_recovers_unseparated_pdf_consignee(self):
        entry = parse("Consignee (Non-Negotiable) BALL & DOGGETT AUSTRALIA PTY LTD")[0]
        self.assertEqual("Consignee (Non-Negotiable)", entry.label)
        self.assertEqual("BALL & DOGGETT AUSTRALIA PTY LTD", entry.raw)

    def test_all_roadmap_aliases_resolve(self):
        cases = {
            "Shipper (Principal or Seller)": "shipper", "To the Order of": "consignee",
            "Notify Party/Intermediate Consignee": "notify_party", "Port of Loading (POL)": "port_of_loading",
            "Discharge Port": "port_of_discharge", "No. of Containers or Packages": "container_count",
            "TOTAL Gross Weight (KG)": "gross_weight_kg", "TOTAL GROSS WEIGHT": "gross_weight_kg",
            "Gross Weight毛重(KGS)": "gross_weight_kg", "Gross Wt (kgs) (毛重 KGS)": "gross_weight_kg",
        }
        for label, field in cases.items():
            self.assertEqual(field, resolve(label)[0], label)

    def test_normalizers_keep_real_differences_and_remove_format_noise(self):
        self.assertEqual("APRIL FAR EAST M SDN BHD", normalize("shipper", "April Far East (M) Sdn. Bhd."))
        self.assertEqual("NANTONG CHINA", normalize("port_of_loading", "Nantong, China (CNNTG)"))
        self.assertEqual("6", normalize("container_count", "6 x 40'HC"))
        self.assertEqual("131058", normalize("gross_weight_kg", "131,058 KG"))
        self.assertEqual("341715", normalize("gross_weight_kg", "341.715 MT"))
        self.assertIsNone(normalize("gross_weight_kg", "____MT"))

    def test_total_pdf_rows_win_over_per_container_rows(self):
        text = """BILL OF LADING (DRAFT)
========================================
Gross Weight (KG): 100 KG
TOTAL Gross Weight (KG): 200 KG
Container Count: 1 x 40'HC
No. of Containers: 2 x 40'HC
"""
        results, _ = extract_text(text, "demo")
        fields = {item.field: item for item in results}
        self.assertEqual("200", fields["gross_weight_kg"].normalized)
        self.assertEqual("2", fields["container_count"].normalized)

    def test_placeholders_are_blank_and_learned_aliases_are_explicit(self):
        text = """SHIPPING INSTRUCTION
========================================
Cargo Weight: ____MT
"""
        results, extras = extract_text(text, "demo", learned={"Cargo Weight": "gross_weight_kg"})
        fields = {item.field: item for item in results}
        self.assertEqual("blank", fields["gross_weight_kg"].status)
        self.assertIsNone(fields["gross_weight_kg"].normalized)
        self.assertEqual([], extras)

    def test_explicit_non_shipping_marker_is_excluded_from_coverage(self):
        from backend.app.extract.pipeline import _comparable

        self.assertFalse(_comparable({}, "*** PACKING LIST ONLY - NO PORT OR VESSEL DETAILS ***"))


class ExtractionPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(cls.temporary_directory.name)
        cls.settings = settings_from_env({"DATA_DIR": PROJECT_ROOT / "data", "DATABASE_PATH": root / "index.sqlite3", "DERIVED_DIR": root / "derived"})
        ingest(cls.settings, reset=True)
        convert_all(cls.settings)
        extract_all(cls.settings)

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    def test_every_comparable_document_has_all_seven_persisted_results(self):
        with database(self.settings.database_path) as connection:
            rows = connection.execute("SELECT doc_id, COUNT(*) AS count FROM extractions GROUP BY doc_id").fetchall()
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row["count"] == len(FIELDS) for row in rows))
        self.assertNotIn("email_501_BL", {row["doc_id"] for row in rows})

        extract_all(self.settings)
        with database(self.settings.database_path) as connection:
            rerun_rows = connection.execute("SELECT doc_id, COUNT(*) AS count FROM extractions GROUP BY doc_id").fetchall()
        self.assertEqual([(row["doc_id"], row["count"]) for row in rows], [(row["doc_id"], row["count"]) for row in rerun_rows])

    def test_known_pair_extracts_values_and_writes_reports(self):
        with database(self.settings.database_path) as connection:
            values = {row["field"]: row for row in connection.execute("SELECT field, normalized, status, line_no, confidence FROM extractions WHERE doc_id = 'email_004_SI'")}
        self.assertEqual("found", values["shipper"]["status"])
        self.assertEqual(1.0, values["shipper"]["confidence"])
        self.assertEqual("6", values["container_count"]["normalized"])
        self.assertEqual("131058", values["gross_weight_kg"]["normalized"])
        self.assertIsNotNone(values["shipper"]["line_no"])
        report = write_reports(self.settings)
        self.assertIn(".txt", report["formats"])
        self.assertGreater(report["documents"]["excluded_wrong_type"], 0)
        self.assertEqual({}, report["readable_missing"])
        self.assertGreater(report["unreadable_documents"].get(".pdf", 0), 0)
        self.assertTrue((self.settings.derived_dir / "extraction_coverage.json").is_file())
        self.assertTrue((self.settings.derived_dir / "unknown_labels.json").is_file())


if __name__ == "__main__":
    unittest.main()
