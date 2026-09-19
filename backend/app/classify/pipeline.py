"""Persist deterministic classifications and optionally use Gemini only for uncertainty."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from ..config import Settings
from ..db import database, initialize
from . import gemini, rules
from .features import build_features


@dataclass(frozen=True)
class ClassificationRun:
    categories: dict[str, int]
    decisions: dict[str, int]
    skipped: int
    gemini_calls: int


def classify_all(settings: Settings, *, use_gemini: bool = False, force: bool = False) -> ClassificationRun:
    """Classify only non-overridden mail; saved classifications make reruns free."""
    initialize(settings.database_path)
    with database(settings.database_path) as connection:
        emails = [dict(row) for row in connection.execute("SELECT * FROM emails ORDER BY email_id")]
        document_rows = connection.execute("SELECT * FROM documents ORDER BY doc_id").fetchall()
    documents_by_email: dict[str, list[dict]] = {}
    for row in document_rows:
        documents_by_email.setdefault(row["email_id"], []).append(dict(row))

    decisions: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    skipped = gemini_calls = 0
    updates: list[tuple[str, float, str, str, str]] = []
    for email in emails:
        if email["category_override"] or (not force and email["category"] != "UNCLASSIFIED"):
            skipped += 1
            categories[email["category"]] += 1
            continue
        features = build_features(email, documents_by_email.get(email["email_id"], []), settings.derived_dir)
        decision = rules.classify(features)
        decided_by = "rule"
        if decision is None or decision.confidence < 0.75:
            llm = gemini.classify(features, settings.derived_dir) if use_gemini else None
            if llm is not None:
                decision = rules.RuleDecision(llm.category, llm.confidence, (llm.reason,))
                decided_by = "llm"
                gemini_calls += not llm.cached
        if decision is None:
            decision = rules.RuleDecision("GENERAL", 0.45, ("no_high_confidence_rule; safe_general_fallback",))
        updates.append((decision.category, decision.confidence, json.dumps(decision.reasons), decided_by, email["email_id"]))
        categories[decision.category] += 1
        decisions[decided_by] += 1

    with database(settings.database_path) as connection:
        connection.executemany("UPDATE emails SET category = ?, category_conf = ?, category_reasons = ?, decided_by = ? WHERE email_id = ?", updates)
        for _, _, _, _, email_id in updates:
            connection.execute("INSERT INTO stage_runs (email_id, stage, state) VALUES (?, 'classify', 'ok') ON CONFLICT(email_id, stage) DO UPDATE SET state = 'ok', error = NULL, updated_at = CURRENT_TIMESTAMP", (email_id,))
    return ClassificationRun(dict(sorted(categories.items())), dict(sorted(decisions.items())), skipped, gemini_calls)
