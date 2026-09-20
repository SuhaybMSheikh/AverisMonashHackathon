# Dev-label error analysis — round 2

Scope: the 40 IDs in `dev_labels/dev_labels.json`. The labels passed validation:
all IDs exist, values use the allowed schema, and status/field consistency is
valid. The comparison below uses the prior round report as the baseline. Since
three labels were updated before this round, changes combine those label
corrections with the general rule and party-policy changes described below.

Gemini API key set: **no**. No Gemini request was made. `decided_by` was
`rule: 520` before and after this round.

## Metric comparison

| Metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| BL_COMPARISON F1 | 1.0000 | 1.0000 | 0.0000 |
| GENERAL F1 | 0.5263 | 1.0000 | +0.4737 |
| INVOICE_QUERY F1 | 0.4000 | 1.0000 | +0.6000 |
| SI_REQUEST F1 | 0.7273 | 1.0000 | +0.2727 |
| SPAM F1 | 0.4000 | 1.0000 | +0.6000 |
| Macro-F1 | 0.6107 | 1.0000 | +0.3893 |
| Defect precision | 0.8462 (11 TP, 2 FP) | 1.0000 (11 TP, 0 FP) | +0.1538 |
| Defect recall | 1.0000 (0 FN) | 1.0000 (0 FN) | 0.0000 |
| Defect F1 | 0.9167 | 1.0000 | +0.0833 |
| Exact field-set match | 0.9500 | 1.0000 | +0.0500 |
| End-to-end rate | 0.6750 | 0.9500 | +0.2750 |
| Escalation precision | 0.6667 (4 TP, 2 FP) | 0.6667 (4 TP, 2 FP) | 0.0000 |
| Escalation recall | 1.0000 (0 FN) | 1.0000 (0 FN) | 0.0000 |
| Escalation F1 | 0.8000 | 0.8000 | 0.0000 |
| Review-reason accuracy | 1.0000 | 1.0000 | 0.0000 |

### Category confusion matrices

Before (rows expected, columns predicted):

| Expected \ Predicted | BL | GENERAL | INVOICE | SI | SPAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| BL_COMPARISON | 20 | 0 | 0 | 0 | 0 |
| GENERAL | 0 | 5 | 0 | 0 | 0 |
| INVOICE_QUERY | 0 | 3 | 1 | 0 | 0 |
| SI_REQUEST | 0 | 3 | 0 | 4 | 0 |
| SPAM | 0 | 3 | 0 | 0 | 1 |

After:

| Expected \ Predicted | BL | GENERAL | INVOICE | SI | SPAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| BL_COMPARISON | 22 | 0 | 0 | 0 | 0 |
| GENERAL | 0 | 6 | 0 | 0 | 0 |
| INVOICE_QUERY | 0 | 0 | 4 | 0 | 0 |
| SI_REQUEST | 0 | 0 | 0 | 4 | 0 |
| SPAM | 0 | 0 | 0 | 0 | 4 |

## General-rule scope audit

Each rule is pattern-based; none identifies an email, sender, or company. “Other”
excludes the reviewed dev-label IDs. Examples are email IDs for precision review.

| Rule | Total fires | Other emails | First ten examples |
| --- | ---: | ---: | --- |
| No-attachment draft-BL checking request → BL_COMPARISON/OK | 94 | 92 | email_003, email_006, email_016, email_018, email_036, email_038, email_047, email_049, email_050, email_061 |
| Invoice cancellation/reversal → INVOICE_QUERY | 12 | 10 | email_108, email_191, email_236, email_269, email_274, email_280, email_298, email_403, email_406, email_425 |
| Detention/demurrage charge query → INVOICE_QUERY | 18 | 17 | email_017, email_041, email_045, email_048, email_165, email_224, email_268, email_331, email_355, email_369 |
| Payment-deadline link → SPAM | 6 | 5 | email_116, email_134, email_329, email_387, email_404, email_449 |
| Advance-fee financial solicitation → SPAM | 7 | 6 | email_226, email_345, email_363, email_382, email_390, email_417, email_455 |
| Unsolicited high-discount promotion → SPAM | 7 | 6 | email_026, email_150, email_180, email_184, email_188, email_222, email_470 |

The draft-BL rule produces `BL_COMPARISON`, `OK`, no defect fields, no review
reason, and `decided_by="rule"`. The party policy compares a normalized first
line as the name; it compares address lines only when both sides provide them.
An address on one side only now records an informational note rather than a
mismatch.

## Remaining misses (2)

| Email | Expected → predicted | Evidence and source text | Cause |
| --- | --- | --- | --- |
| email_512 | BL_COMPARISON / OK → BL_COMPARISON / NEEDS_REVIEW (`unreadable`) | The label’s visual review says all seven fields match. Both source conversions failed: `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_512_SI.txt` and `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_512_BL.txt`. | Converter/OCR coverage is insufficient, so the deterministic status policy conservatively escalates. |
| email_513 | BL_COMPARISON / OK → BL_COMPARISON / NEEDS_REVIEW (`unreadable`) | The label’s visual review says all seven fields match. Both source conversions failed: `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_513_SI.txt` and `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_513_BL.txt`. | Converter/OCR coverage is insufficient, so the deterministic status policy conservatively escalates. |

No further fixes were implemented for those scans. The reported `unreadable`
outcomes remain appropriate until a general scan-conversion improvement is
validated.

## Verification

- `uv run --locked python -m unittest discover -s backend/tests -q`: 50 tests passed.
- `npm --prefix frontend run check`: passed.
- `uv run --locked python -m scripts.eval_dev --labels dev_labels/dev_labels.json --show-misses --output NUL`: ran successfully and reported the two misses above.
