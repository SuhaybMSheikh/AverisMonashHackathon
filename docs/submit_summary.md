# Submission summary — Round 2

Round 2 was the single approved full submission, made on 2026-09-20.  It used
all 520 emails and the guarded submission script; no individual-email probes
were made.  The comparison is against the baseline recorded in
`docs/score_log.md`.

| Component | Baseline | Round 2 | Change |
|---|---:|---:|---:|
| Final score | 0.192565 | 1.000000 | +0.807435 |
| Emails scored | 520 | 520 | 0 |
| Stage 1 accuracy | 0.698077 | 1.000000 | +0.301923 |
| Stage 1 macro-F1 | 0.641882 | 1.000000 | +0.358118 |
| Stage 3 defect precision | 0.000000 | 1.000000 | +1.000000 |
| Stage 3 defect recall | 0.000000 | 1.000000 | +1.000000 |
| Stage 3 defect F1 | 0.000000 | 1.000000 | +1.000000 |
| Stage 3 field F1 | 0.000000 | 1.000000 | +1.000000 |
| Stage 3 exact field-set match | 0.770000 | 1.000000 | +0.230000 |
| Comparable documents | 200 | 200 | 0 |
| End-to-end success | 0 / 46 | 46 / 46 | +46 |
| End-to-end rate | 0.000000 | 1.000000 | +1.000000 |
| Escalation precision | 0.134921 | 1.000000 | +0.865079 |
| Escalation recall | 0.850000 | 0.850000 | 0.000000 |
| Escalation F1 | 0.232877 | 0.918919 | +0.686042 |
| Predicted review cases | 126 | 17 | -109 |
| Gold review cases | 20 | 20 | 0 |

## Stage 1 per-category results

| Category | Baseline TP / FP / FN | Round 2 TP / FP / FN |
|---|---:|---:|
| BL_COMPARISON | 126 / 0 / 94 | 220 / 0 / 0 |
| GENERAL | 60 / 157 / 0 | 60 / 0 / 0 |
| INVOICE_QUERY | 45 / 0 / 30 | 75 / 0 / 0 |
| SI_REQUEST | 125 / 0 / 0 | 125 / 0 / 0 |
| SPAM | 7 / 0 / 33 | 40 / 0 / 0 |

The Round 2 confusion matrix is diagonal: BL_COMPARISON 220, GENERAL 60,
INVOICE_QUERY 75, SI_REQUEST 125, and SPAM 40.  The baseline off-diagonal
counts were BL_COMPARISON → GENERAL 94, INVOICE_QUERY → GENERAL 30, and SPAM
→ GENERAL 33.

## Reliability detail

| Review reason | Baseline caught / total | Round 2 caught / total |
|---|---:|---:|
| missing_attachment | 2 / 5 | 2 / 5 |
| missing_value | 5 / 5 | 5 / 5 |
| unreadable | 5 / 5 | 5 / 5 |
| wrong_doc_type | 5 / 5 | 5 / 5 |

The scoring weights were unchanged: Stage 1 0.3, Stage 3 0.2, end-to-end 0.5.
The result agrees with the current limited dev-set signal, so no post-score
decision changes were made.  The dev-set provenance limitation remains: it was
labeled by one reviewer and is not independent corroboration; see
`docs/phase12_limitations.md`.
