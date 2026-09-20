from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.submit_submission import append_score_log, logged_submission_hashes, submission_sha256


class SubmissionScriptTests(unittest.TestCase):
    def test_score_log_records_complete_response_and_detects_duplicate_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            submission = root / "submission.json"
            submission.write_text('{"email_001": {}}\n', encoding="utf-8")
            log = root / "docs" / "score_log.md"
            digest = submission_sha256(submission)
            result = {"stage_1": 0.5, "stage_3": 0.6, "reliability": {"f1": 0.7}}

            append_score_log(note="baseline", digest=digest, result=result, log_path=log)

            self.assertEqual({digest}, logged_submission_hashes(log))
            text = log.read_text(encoding="utf-8")
            self.assertIn("- Note: baseline", text)
            self.assertIn('"stage_1": 0.5', text)
            self.assertIn('"stage_3": 0.6', text)
            self.assertIn('"reliability": {', text)


if __name__ == "__main__":
    unittest.main()
