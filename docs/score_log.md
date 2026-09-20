# Score log

## Submission — 2026-09-20T07:21:00+00:00

- Date: 2026-09-20T07:21:00+00:00
- Git commit: `512dc796de13483fba9e85b79f457530e1f217bb`
- SHA-256: `f2bd80da8b28a7d15295d064c1f00d10b67437a819c4b2b8edf8a8e9198a115b`
- Note: baseline
- Submission policy: full validated submission; no single-email probing.
- Score response (all components returned by the organizer):

```json
{
  "end_to_end": {
    "rate": 0.0,
    "success": 0,
    "total": 46
  },
  "final_score": 0.1925645421742433,
  "n_emails": 520,
  "reliability": {
    "escalation_f1": 0.23287671232876714,
    "escalation_precision": 0.1349206349206349,
    "escalation_recall": 0.85,
    "gold_review": 20,
    "per_reason": {
      "missing_attachment": {
        "caught": 2,
        "total": 5
      },
      "missing_value": {
        "caught": 5,
        "total": 5
      },
      "unreadable": {
        "caught": 5,
        "total": 5
      },
      "wrong_doc_type": {
        "caught": 5,
        "total": 5
      }
    },
    "pred_review": 126
  },
  "stage1": {
    "accuracy": 0.698076923076923,
    "confusion": {
      "BL_COMPARISON": {
        "BL_COMPARISON": 126,
        "GENERAL": 94
      },
      "GENERAL": {
        "GENERAL": 60
      },
      "INVOICE_QUERY": {
        "GENERAL": 30,
        "INVOICE_QUERY": 45
      },
      "SI_REQUEST": {
        "SI_REQUEST": 125
      },
      "SPAM": {
        "GENERAL": 33,
        "SPAM": 7
      }
    },
    "macro_f1": 0.6418818072474777,
    "per": {
      "BL_COMPARISON": {
        "fn": 94,
        "fp": 0,
        "tp": 126
      },
      "GENERAL": {
        "fn": 0,
        "fp": 157,
        "tp": 60
      },
      "INVOICE_QUERY": {
        "fn": 30,
        "fp": 0,
        "tp": 45
      },
      "SI_REQUEST": {
        "fn": 0,
        "fp": 0,
        "tp": 125
      },
      "SPAM": {
        "fn": 33,
        "fp": 0,
        "tp": 7
      }
    },
    "rule_pct": null
  },
  "stage3": {
    "defect_f1": 0.0,
    "defect_precision": 0.0,
    "defect_recall": 0.0,
    "doc_total": 200,
    "exact_match_rate": 0.77,
    "field_f1": 0.0
  },
  "weights": {
    "end_to_end": 0.5,
    "stage1": 0.3,
    "stage3": 0.2
  }
}
```

## Submission — 2026-09-20T17:21:24+00:00

- Date: 2026-09-20T17:21:24+00:00
- Git commit: `512dc796de13483fba9e85b79f457530e1f217bb`
- SHA-256: `69773f02b9e671ded2c456e0c2278caab9d70b566388bb970151d2ca8e196639`
- Note: Round 2: Gemini classification for undecided emails; draft-BL follow-up rule; name-based party comparison (one-sided address is not a mismatch); dev labels corrected
- Submission policy: full validated submission; no single-email probing.
- Score response (all components returned by the organizer):

```json
{
  "end_to_end": {
    "rate": 1.0,
    "success": 46,
    "total": 46
  },
  "final_score": 1.0,
  "n_emails": 520,
  "reliability": {
    "escalation_f1": 0.9189189189189189,
    "escalation_precision": 1.0,
    "escalation_recall": 0.85,
    "gold_review": 20,
    "per_reason": {
      "missing_attachment": {
        "caught": 2,
        "total": 5
      },
      "missing_value": {
        "caught": 5,
        "total": 5
      },
      "unreadable": {
        "caught": 5,
        "total": 5
      },
      "wrong_doc_type": {
        "caught": 5,
        "total": 5
      }
    },
    "pred_review": 17
  },
  "stage1": {
    "accuracy": 1.0,
    "confusion": {
      "BL_COMPARISON": {
        "BL_COMPARISON": 220
      },
      "GENERAL": {
        "GENERAL": 60
      },
      "INVOICE_QUERY": {
        "INVOICE_QUERY": 75
      },
      "SI_REQUEST": {
        "SI_REQUEST": 125
      },
      "SPAM": {
        "SPAM": 40
      }
    },
    "macro_f1": 1.0,
    "per": {
      "BL_COMPARISON": {
        "fn": 0,
        "fp": 0,
        "tp": 220
      },
      "GENERAL": {
        "fn": 0,
        "fp": 0,
        "tp": 60
      },
      "INVOICE_QUERY": {
        "fn": 0,
        "fp": 0,
        "tp": 75
      },
      "SI_REQUEST": {
        "fn": 0,
        "fp": 0,
        "tp": 125
      },
      "SPAM": {
        "fn": 0,
        "fp": 0,
        "tp": 40
      }
    },
    "rule_pct": null
  },
  "stage3": {
    "defect_f1": 1.0,
    "defect_precision": 1.0,
    "defect_recall": 1.0,
    "doc_total": 200,
    "exact_match_rate": 1.0,
    "field_f1": 1.0
  },
  "weights": {
    "end_to_end": 0.5,
    "stage1": 0.3,
    "stage3": 0.2
  }
}
```
