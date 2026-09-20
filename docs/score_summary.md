# Baseline score summary

This report interprets the single baseline submission recorded in
[`score_log.md`](score_log.md). It describes only aggregate organizer metrics;
it does not inspect individual emails or change any pipeline decision.

## Overall result

- **Final score:** 0.1926
- **Scored emails:** 520
- **Weighted calculation:** `0.30 × stage 1 macro-F1 (0.6419) + 0.20 × stage 3 field-F1 (0.0000) + 0.50 × end-to-end rate (0.0000) = 0.1926`.

The final score is entirely supplied by classification. The weighted defect and
end-to-end components contribute zero, and end-to-end carries the largest
weight (50%).

## Component interpretation

| Component | Baseline result | Meaning | Aggregate reading |
| --- | ---: | --- | --- |
| Stage 1 classification | Accuracy 0.6981; macro-F1 0.6419 | Routes each email into one of the five operational categories. Macro-F1 gives every category equal weight. | Moderate overall performance. The aggregate confusion matrix shows 94 BL-comparison, 30 invoice-query, and 33 spam emails routed to General; SI-request has no listed false negatives. This pattern can reduce downstream comparison coverage and explains part of the zero end-to-end result. |
| Stage 3 defect detection | Field-F1 0.0000; precision 0.0000; recall 0.0000; exact-match rate 0.7700 across 200 documents | Detects the exact defective-field set for comparable documents. Field-F1 measures aggregate precision and recall of defects; exact-match is a separate whole-document diagnostic. | This is the weakest diagnostic component. Zero field precision and recall means no defect-field true positives under the scorer. The 0.7700 exact-match rate should not be read as successful defect detection by itself; it can coexist with missed defects, false alarms, or both. |
| End-to-end | 0 / 46; rate 0.0000 | Requires the correct routing and exact defect-field outcome on end-to-end cases. | This is the weakest weighted component. A zero rate can result from classification misses, missed defects, extra false-alarm fields, or an escalation where the scorer requires a definitive answer. |
| Reliability / escalation | F1 0.2329; precision 0.1349; recall 0.8500; 126 predicted reviews vs 20 gold reviews | Measures whether genuine human-review cases are escalated. | Recall is high (about 17 of 20 gold review cases caught), while precision is low (about 17 of 126 predicted reviews are gold review cases). The aggregate signal is strong over-escalation, with some remaining under-escalation: missing-attachment catches are 2/5, while the other listed reasons are each 5/5. |

## Relative priorities indicated by the score

1. **End-to-end exactness is the most consequential weakness** because it is zero and accounts for half of the final score. It points to aggregate routing and/or exact-field-set errors rather than a single broad scoring issue.
2. **Defect-field detection is the clearest technical weakness**: both field precision and recall are zero. Likely error classes are missed defects, extra flagged fields, or a combination; the score alone cannot distinguish them.
3. **Escalation is overly broad**: high recall alongside low precision and 126 predicted review cases for 20 gold cases indicates many non-review cases are escalated. The score also indicates incomplete missing-attachment coverage.
4. **Classification is usable but uneven**: macro-F1 is 0.6419, below raw accuracy of 0.6981, consistent with weaker minority/category-balanced performance. The aggregate confusion counts identify General as the main destination for misrouted BL-comparison, invoice-query, and spam mail.

## Provenance

- Submission: `submission.json`
- SHA-256: `f2bd80da8b28a7d15295d064c1f00d10b67437a819c4b2b8edf8a8e9198a115b`
- Source commit: `512dc796de13483fba9e85b79f457530e1f217bb`
- Organizer `stage1.rule_pct`: `null` (not supplied as a numeric rule-share metric)
- Submission count for this baseline: one
