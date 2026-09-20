# Dev-label error analysis

Scope: the 40 entries in `dev_labels/dev_labels.json`; predictions are the
current persisted pipeline results. This report proposes general fixes only;
no code or rules were changed.

## Metrics

### Category confusion matrix

Rows are expected categories; columns are predicted categories.

| Expected \ Predicted | BL_COMPARISON | GENERAL | INVOICE_QUERY | SI_REQUEST | SPAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| BL_COMPARISON | 20 | 0 | 0 | 0 | 0 |
| GENERAL | 0 | 5 | 0 | 0 | 0 |
| INVOICE_QUERY | 0 | 3 | 1 | 0 | 0 |
| SI_REQUEST | 0 | 3 | 0 | 4 | 0 |
| SPAM | 0 | 3 | 0 | 0 | 1 |

| Measure | Result |
| --- | ---: |
| BL_COMPARISON F1 | 1.0000 |
| GENERAL F1 | 0.5263 |
| INVOICE_QUERY F1 | 0.4000 |
| SI_REQUEST F1 | 0.7273 |
| SPAM F1 | 0.4000 |
| Macro-F1 | 0.6107 |
| Defect precision (TP=11, FP=2) | 0.8462 |
| Defect recall (FN=0) | 1.0000 |
| Defect F1 | 0.9167 |
| Exact field-set match | 0.9500 |
| End-to-end rate | 0.6750 |
| Escalation precision (TP=4, FP=2) | 0.6667 |
| Escalation recall (FN=0) | 1.0000 |
| Escalation F1 | 0.8000 |

## Misses by cause

| Cause | Count | General proposed fix |
| --- | ---: | --- |
| Classification rule — invoice intent | 3 | Add high-precision, generic invoice-intent signals for invoice cancellation/reversal, PGI reversal, and D&D/detention charge queries. |
| Classification rule — spam intent | 3 | Add generic, multi-signal spam rules for phishing payment links, implausible financial proposals, and unsolicited high-discount promotions. |
| Classification rule — SI intent | 3 | Separate actual SI content from a request about future SI or draft BL; require shipping-field content or an attached SI before assigning SI_REQUEST. |
| Normalization — party address suffix | 2 | Compare a structured party name separately from an optional address suffix, preserving a mismatch when both primary names differ. |
| Converter — unreadable scan | 2 | Improve the generic scan conversion/OCR fallback and make its coverage threshold explicit before returning a non-review result. |

## Every miss

### Classification rule: invoice intent (3)

| Email | Expected → predicted | Evidence note | Source text | Cause and proposed general fix | Label potentially wrong? |
| --- | --- | --- | --- | --- | --- |
| email_331 | INVOICE_QUERY / OK → GENERAL / OK | Asks to confirm D&D / detention charges before payment release. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_331.json` | Classification rule missed a detention-charge invoice query. Add generic D&D/detention + payment/charge intent. | No; the evidence is a direct invoice-query request. |
| email_298 | INVOICE_QUERY / OK → GENERAL / OK | Requests invoice cancellation and PGI reversal after a booking amendment. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_298.json` | Classification rule missed invoice cancellation/reversal language. Add generic cancellation/reversal + invoice/PGI intent. | No; the evidence directly names an invoice. |
| email_406 | INVOICE_QUERY / OK → GENERAL / OK | Requests invoice cancellation and PGI reversal after a booking amendment. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_406.json` | Same generic invoice-cancellation gap; do not key on this email or company. | No; the evidence directly names an invoice. |

### Classification rule: spam intent (3)

| Email | Expected → predicted | Evidence note | Source text | Cause and proposed general fix | Label potentially wrong? |
| --- | --- | --- | --- | --- | --- |
| email_222 | SPAM / OK → GENERAL / OK | Unsolicited 90%-off logistics-software promotion with urgent buy-now language. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_222.json` | Classification rule lacks an unsolicited-promotion pattern. Require multiple generic commercial-spam signals before SPAM. | No; the sales promotion and urgency are clear. |
| email_345 | SPAM / OK → GENERAL / OK | Purported bank officer offers a USD 4.5m proposal and requests bank details. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_345.json` | Classification rule lacks an advance-fee/financial-solicitation pattern. Add a generic high-risk financial solicitation rule. | No; the request for bank details supports SPAM. |
| email_134 | SPAM / OK → GENERAL / OK | Parcel-payment demand with a 24-hour deadline and tracking link. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_134.json` | Classification rule lacks a phishing payment-link pattern. Add generic payment-deadline + external-link signals. | No; the payment demand and urgency are clear. |

### Classification rule: SI intent (3)

| Email | Expected → predicted | Evidence note | Source text | Cause and proposed general fix | Label potentially wrong? |
| --- | --- | --- | --- | --- | --- |
| email_003 | SI_REQUEST / OK → GENERAL / OK | Requests a draft BL for checking, but provides no shipping instructions. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_003.json` | Predicted GENERAL follows the existing generic future-draft request rule. Do not broaden SI_REQUEST without actual SI content. | **Yes.** The evidence is a future draft-BL request rather than shipping instructions. |
| email_018 | SI_REQUEST / OK → GENERAL / OK | Requests a draft BL for checking and references prior instructions, but provides no current SI fields. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_018.json` | Predicted GENERAL follows the generic future-draft request rule. Keep any SI rule dependent on actual SI fields or an attached SI. | **Yes.** The label relies on prior instructions not present in this email. |
| email_021 | SI_REQUEST / OK → GENERAL / OK | Reminds recipients to submit SI/AED and references an outstanding list. | `C:\Suhayb PC\AverisMonashHackathon\data\inbox\email_021.json` | Rule boundary is ambiguous: it is an administrative reminder, not shipping instructions. Classify reminders only after a policy decision. | **Possibly.** The text requests SI submission but does not itself contain an SI. |

### Normalization: party address suffix (2)

| Email | Expected → predicted | Evidence note | Source text | Cause and proposed general fix | Label potentially wrong? |
| --- | --- | --- | --- | --- | --- |
| email_059 | BL_COMPARISON / OK → BL_COMPARISON / MISMATCH (`consignee`) | Label says the SI and draft BL agree on BALL & DOGGETT AUSTRALIA PTY LTD. SI adds a street address; BL has only the company name. | `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_059_SI.txt`; `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_059_BL.txt` | Normalization compares the full party string. Separate shared legal name from optional address suffix before comparison. | **Possibly.** Treating full consignee addresses as material would make the label's empty field set too permissive. |
| email_208 | BL_COMPARISON / OK → BL_COMPARISON / MISMATCH (`consignee`) | Label says CERIEX agrees. SI adds `ZONE INDUSTRIELLE; CONAKRY, GUINEA`; BL has CERIEX only. | `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_208_SI.txt`; `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_208_BL.txt` | Same party-address suffix issue; use a general structured-party policy, not a company-specific exception. | **Possibly.** The policy must decide whether omitted consignee addresses are material. |

### Converter: unreadable scan (2)

| Email | Expected → predicted | Evidence note | Source text | Cause and proposed general fix | Label potentially wrong? |
| --- | --- | --- | --- | --- | --- |
| email_512 | BL_COMPARISON / OK → BL_COMPARISON / NEEDS_REVIEW (`unreadable`) | Visual review says all seven fields agree, but both scan conversions are recorded as failed. | `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_512_SI.txt`; `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_512_BL.txt` (both failed conversion) | Converter/OCR did not produce usable canonical text. Improve generic scan fallback; retain review when coverage is insufficient. | **Possibly under the automated status policy.** A visual reviewer may establish OK, but failed conversions support NEEDS_REVIEW. |
| email_513 | BL_COMPARISON / OK → BL_COMPARISON / NEEDS_REVIEW (`unreadable`) | Visual review says all seven fields agree, but both scan conversions are recorded as failed. | `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_513_SI.txt`; `C:\Suhayb PC\AverisMonashHackathon\backend\derived\text\email_513_BL.txt` (both failed conversion) | Same generic scan-conversion gap; use a reader fallback and coverage gate rather than an email-specific exception. | **Possibly under the automated status policy.** The human visual conclusion conflicts with failed canonical conversion. |

No fixes were implemented.
