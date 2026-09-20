# Dev-label evaluation — latest

Scope: the 40 IDs in `dev_labels/dev_labels.json` only. The labels passed the
requested schema and inbox-ID validation before evaluation.

## Invocation note

The requested `--show-misses` CLI option is not implemented by the current
`scripts/eval_dev.py`; the module rejects it as an unrecognised argument. Its
unchanged `evaluate()` function was therefore run against the same labels and
the current persisted submission rows. The detailed miss output is in
`docs/error_analysis.md`.

## Evaluator output

```json
{
  "confusion_matrix": {
    "BL_COMPARISON": {"BL_COMPARISON": 20},
    "GENERAL": {"GENERAL": 5},
    "INVOICE_QUERY": {"GENERAL": 3, "INVOICE_QUERY": 1},
    "SI_REQUEST": {"GENERAL": 3, "SI_REQUEST": 4},
    "SPAM": {"GENERAL": 3, "SPAM": 1}
  },
  "defect_f1": 0.9166666666666666,
  "end_to_end_rate": 0.675,
  "escalation_f1": 0.8,
  "exact_field_set_match": 0.95,
  "labels": 40,
  "macro_f1": 0.6107177033492823,
  "per_class_f1": {
    "BL_COMPARISON": 1.0,
    "GENERAL": 0.5263157894736842,
    "INVOICE_QUERY": 0.4,
    "SI_REQUEST": 0.7272727272727273,
    "SPAM": 0.4
  },
  "review_reason_accuracy": 1.0,
  "review_reason_labels": 4
}
```

