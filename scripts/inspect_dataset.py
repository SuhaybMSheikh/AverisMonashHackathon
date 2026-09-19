"""Print observed participant-bundle facts without classifying or modifying inputs."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings_from_env
from backend.app.loader import Inbox


def describe_pair(attachments: list[str]) -> str:
    # Preserve SI/BL attachment order so this mirrors the facts in the roadmap.
    formats = [Path(path).suffix.lower().lstrip(".") for path in attachments]
    return "+".join(formats) if formats else "none"


def main() -> None:
    settings = settings_from_env()
    inbox = Inbox(settings.data_dir)
    emails = inbox.emails()
    attachments = [path for email in emails for path in email.get("attachments", [])]
    format_counts = Counter(Path(path).suffix.lower() for path in attachments)
    pair_counts = Counter(
        describe_pair(email["attachments"])
        for email in emails
        if len(email.get("attachments", [])) == 2
    )
    no_attachments = sum(not email.get("attachments") for email in emails)
    single_attachments = sum(len(email.get("attachments", [])) == 1 for email in emails)

    print(f"Emails: {len(emails)}")
    print(f"Attachments: {len(attachments)}")
    print("Formats:")
    for extension, count in sorted(format_counts.items()):
        print(f"  {extension}: {count}")
    print("Two-document format pairs:")
    for pair, count in sorted(pair_counts.items()):
        print(f"  {pair}: {count}")
    print(f"Emails without attachments: {no_attachments}")
    print(f"Emails with one attachment: {single_attachments}")


if __name__ == "__main__":
    main()
