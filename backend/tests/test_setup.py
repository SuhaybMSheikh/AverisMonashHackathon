import unittest

from loader import Inbox


class ParticipantBundleTests(unittest.TestCase):
    def test_bundle_is_readable_from_data_directory(self):
        inbox = Inbox("data")
        emails = inbox.emails()

        self.assertEqual(520, len(emails))
        self.assertEqual("email_001", emails[0]["email_id"])
        self.assertEqual(
            {"email_id", "from", "subject", "body", "attachments"},
            set(emails[0]),
        )


if __name__ == "__main__":
    unittest.main()
