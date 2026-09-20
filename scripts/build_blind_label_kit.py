"""Build the fixed-seed, source-only blind labeling kit for Phase 12.3."""
from __future__ import annotations

import html
import json
import random
from pathlib import Path

from backend.app.config import PROJECT_ROOT


SEED = 20_260_920
DATA_DIR = PROJECT_ROOT / "data"
CANONICAL_TEXT_DIR = PROJECT_ROOT / "backend" / "derived" / "text"
REVIEW_SHEET = PROJECT_ROOT / "dev_labels" / "review_sheet.md"
TODO_FILE = PROJECT_ROOT / "dev_labels" / "dev_labels.todo.json"

# These are source-format pools reviewed from the participant bundle. They are
# deliberately not labels or pipeline outputs.
TEXT_PDF_IDS = ("email_059", "email_160", "email_208", "email_273", "email_313", "email_351", "email_407", "email_411", "email_434", "email_499")
SCAN_IDS = ("email_512", "email_513", "email_514")
CORRUPT_PDF_IDS = ("email_511", "email_515")
MISLEADING_SUBJECT_IDS = ("email_012", "email_021", "email_230")
SI_REQUEST_IDS = ("email_007", "email_014", "email_054", "email_079", "email_101", "email_135", "email_177", "email_233")
INVOICE_IDS = ("email_002", "email_010", "email_024", "email_060", "email_062", "email_069", "email_074", "email_078")
GENERAL_IDS = ("email_070", "email_083", "email_089", "email_213", "email_234", "email_241", "email_266")
SPAM_IDS = ("email_015", "email_072", "email_123", "email_140", "email_156", "email_204", "email_206", "email_215")


def _load_emails() -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((DATA_DIR / "inbox").glob("email_*.json"))
    }


def _extensions(email: dict) -> tuple[str, ...]:
    return tuple(sorted(Path(path).suffix.lower() for path in email.get("attachments", [])))


def _sample(rng: random.Random, values: tuple[str, ...] | list[str], count: int) -> tuple[str, ...]:
    if len(values) < count:
        raise ValueError(f"need {count} candidates, found {len(values)}")
    return tuple(sorted(rng.sample(sorted(values), count)))


def select_groups() -> dict[str, tuple[str, ...]]:
    """Choose each required source-material stratum deterministically."""
    emails = _load_emails()
    rng = random.Random(SEED)
    paired_txt = tuple(email_id for email_id, email in emails.items() if _extensions(email) == (".txt", ".txt"))
    paired_xlsx = tuple(email_id for email_id, email in emails.items() if _extensions(email) == (".xlsx", ".xlsx"))
    paired_mixed = tuple(email_id for email_id, email in emails.items() if _extensions(email) == (".docx", ".xlsx"))
    missing_attachment = tuple(email_id for email_id, email in emails.items() if len(email.get("attachments", [])) == 1)
    no_attachment_draft = tuple(
        email_id for email_id, email in emails.items()
        if not email.get("attachments") and "send the draft bl" in email.get("body", "").lower()
    )

    return {
        "comparison_txt": _sample(rng, paired_txt, 5),
        "comparison_xlsx": _sample(rng, paired_xlsx, 3),
        "comparison_mixed": _sample(rng, paired_mixed, 3),
        "comparison_text_pdf": _sample(rng, TEXT_PDF_IDS, 3),
        "comparison_scan": _sample(rng, SCAN_IDS, 2),
        "comparison_corrupt_pdf": _sample(rng, CORRUPT_PDF_IDS, 2),
        "comparison_missing_attachment": _sample(rng, missing_attachment, 2),
        "trap_no_attachment_draft": _sample(rng, no_attachment_draft, 2),
        "trap_misleading_subject": _sample(rng, MISLEADING_SUBJECT_IDS, 3),
        "other_si_request": _sample(rng, SI_REQUEST_IDS, 4),
        "other_invoice": _sample(rng, INVOICE_IDS, 4),
        "other_general": _sample(rng, GENERAL_IDS, 3),
        "other_spam": _sample(rng, SPAM_IDS, 4),
    }


def select_ids() -> tuple[tuple[str, ...], frozenset[str]]:
    """Return forty stable IDs and the twenty records that have paired documents."""
    groups = select_groups()
    comparison_ids = frozenset(
        item for name, group in groups.items() if name.startswith("comparison_") for item in group
    )
    other_groups = tuple(group for name, group in groups.items() if not name.startswith("comparison_"))
    selected = tuple(sorted((*comparison_ids, *(item for group in other_groups for item in group))))
    if len(comparison_ids) != 20 or len(selected) != 40:
        raise ValueError("selection no longer satisfies the required 20 comparison / 40 total split")
    if len(set(selected)) != len(selected):
        raise ValueError("selection contains duplicate email IDs")
    return selected, comparison_ids


def _canonical_text(email_id: str, suffix: str) -> str:
    path = CANONICAL_TEXT_DIR / f"{email_id}_{suffix}.txt"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        text = ""
    return text or "[Canonical text unavailable for this attachment.]"


def _pre(value: str) -> str:
    return f"<pre>{html.escape(value)}</pre>"


def _email_block(number: int, email: dict, *, paired: bool) -> str:
    metadata = (
        f"- **ID:** `{email['email_id']}`\n"
        f"- **From:** {email.get('from', '')}\n"
        f"- **Subject:** {email.get('subject', '')}\n\n"
        f"**Body**\n\n{_pre(email.get('body', ''))}\n"
    )
    if not paired:
        return f"## Email {number}\n\n{metadata}\n"
    documents = (
        "<table><tr>"
        "<th align=\"left\">Shipping instruction — canonical text</th>"
        "<th align=\"left\">Draft bill of lading — canonical text</th>"
        "</tr><tr>"
        f"<td valign=\"top\">{_pre(_canonical_text(email['email_id'], 'SI'))}</td>"
        f"<td valign=\"top\">{_pre(_canonical_text(email['email_id'], 'BL'))}</td>"
        "</tr></table>\n"
    )
    return f"## Email {number}\n\n{metadata}\n{documents}\n"


def write_kit() -> tuple[tuple[str, ...], frozenset[str]]:
    """Write review material with no suggested category, verdict, or field labels."""
    selected, paired = select_ids()
    emails = _load_emails()
    review = [
        "# Blind review sheet",
        "",
        f"Fixed selection seed: `{SEED}`. Review source material only; the companion TODO file intentionally contains no suggested labels, verdicts, review reasons, or defect fields.",
        "",
    ]
    review.extend(_email_block(number, emails[email_id], paired=email_id in paired) for number, email_id in enumerate(selected, start=1))
    TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_SHEET.write_text("\n".join(review), encoding="utf-8", newline="\n")
    todo = {
        email_id: {"category": "", "status": "", "review_reason": "", "defect_fields": [], "evidence": ""}
        for email_id in selected
    }
    TODO_FILE.write_text(json.dumps(todo, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return selected, paired


def main() -> None:
    selected, paired = write_kit()
    print(f"wrote {len(selected)} blind review records ({len(paired)} paired-document records) with seed {SEED}")


if __name__ == "__main__":
    main()
