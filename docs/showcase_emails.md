# Demo showcase emails

Run the full pipeline before the demo and confirm each current verdict in the
dashboard. The intended story is below; source documents remain the evidence.

| Email | Demo moment | Expected handling |
|---|---|---|
| `email_004` | Party mismatch | Mismatch with SI reference and BL difference visible |
| `email_499` | Weight mismatch | Mismatch; explain the 1,000 kg difference |
| `email_055` | Mixed formats | XLSX SI and DOCX BL shown through canonical text |
| `email_005` | Clean check or format-only confirmation | No mismatch when values differ only in representation |
| `email_512` | Scan risk | Needs review because OCR confidence is insufficient |
| `email_511` | Corrupt PDF | Needs review with unreadable evidence and retry path |
| `email_507` | Missing BL | Needs review with missing-attachment follow-up |
| `email_003` | Classification trap | General, despite the draft-BL wording and absent attachments |

Use five to six of these in a four-minute demo; retain the other two as backup.
