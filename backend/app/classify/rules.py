"""Small transparent rules for high-confidence inbox routing."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .features import EmailFeatures


CATEGORIES = frozenset({"BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"})
INVOICE_NUMBER = re.compile(r"\binvoice(?:\s*(?:no\.?|number))?\s*[:#-]?\s*\d{5,}\b", re.I)
LINK = re.compile(r"(?:https?://|www\.)", re.I)


@dataclass(frozen=True)
class RuleDecision:
    category: str
    confidence: float
    reasons: tuple[str, ...]


def _contains_any(body: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in body for phrase in phrases)


def classify(features: EmailFeatures) -> RuleDecision | None:
    """Classify from body intent and detected attachment roles, never subject alone."""
    body = features.body.lower()
    roles = set(features.detected_roles)
    has_comparison_pair = {"SI", "BL"}.issubset(roles)
    if has_comparison_pair:
        return RuleDecision("BL_COMPARISON", 0.99, ("detected_si_and_bl_attachments",))

    lure_terms = ("verify your account", "urgent action", "act now", "prize", "winner", "crypto", "bitcoin", "wallet")
    suspicious_domains = ("crypto", "secure-mail", "wallet", "prize", "bonus", "giveaway")
    suspicious_domain = any(token in features.sender_domain for token in suspicious_domains)
    if LINK.search(body) and _contains_any(body, lure_terms) and suspicious_domain:
        return RuleDecision("SPAM", 0.97, ("link", "phishing_lure", "suspicious_sender_domain"))

    charge_terms = ("thc", "local charge", "local charges", "breakdown", "billed", "billing", "freight charge")
    if INVOICE_NUMBER.search(body) and _contains_any(body, charge_terms):
        return RuleDecision("INVOICE_QUERY", 0.96, ("invoice_number", "charge_vocabulary"))

    notice_terms = ("berthing report", "outstanding list", "outstanding bl", "reminder:", "daily summary", "weekly summary")
    if _contains_any(body, notice_terms):
        return RuleDecision("GENERAL", 0.94, ("operational_notice_template",))

    # A supplied single shipping document plus a missing-draft request stays in the
    # comparison queue. The attachment is evidence that a comparison is underway.
    checking_terms = ("checking", "check", "confirm", "compare", "verify")
    if features.attachment_count == 1 and roles.intersection({"SI", "BL"}) and "draft bl" in body and _contains_any(body, checking_terms):
        return RuleDecision("BL_COMPARISON", 0.82, ("single_shipping_document_with_draft_bl_check_request",))
    # O2 policy: without any document, “send the draft BL for checking” is a
    # request for a future document, not evidence that comparison can begin.
    if features.attachment_count == 0 and "draft bl" in body and _contains_any(body, checking_terms):
        return RuleDecision("GENERAL", 0.83, ("draft_bl_request_without_attachment",))

    si_labels = ("pol:", "pod:", "shipper:", "consignee:", "notify party:", "gross wt", "gross weight")
    si_label_count = sum(label in body for label in si_labels)
    if si_label_count >= 3:
        return RuleDecision("SI_REQUEST", 0.93, (f"si_field_labels={si_label_count}",))
    if "shipping instruction" in body and _contains_any(body, ("please find", "please process", "new shipment")):
        return RuleDecision("SI_REQUEST", 0.84, ("shipping_instruction_request",))
    return None
