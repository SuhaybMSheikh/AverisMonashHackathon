"""Small transparent rules for high-confidence inbox routing."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .features import EmailFeatures


CATEGORIES = frozenset({"BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"})
INVOICE_NUMBER = re.compile(r"\binvoice(?:\s*(?:no\.?|number))?\s*[:#-]?\s*\d{5,}\b", re.I)
LINK = re.compile(r"(?:https?://|www\.)", re.I)
URL_OR_DOMAIN = re.compile(r"(?:https?://|www\.|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+\b)", re.I)
DRAFT_BL = re.compile(r"\bdraft\s+(?:b/?l|bill\s+of\s+lading)\b", re.I)
PERCENT_OFF = re.compile(r"\b\d{1,3}\s*%\s*off\b", re.I)


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

    if INVOICE_NUMBER.search(body) and _contains_any(body, ("cancel", "cancellation")) and _contains_any(body, ("reverse", "reversal", "pgi")):
        return RuleDecision("INVOICE_QUERY", 0.96, ("invoice_number", "cancellation", "reversal_or_pgi"))
    if _contains_any(body, ("detention", "demurrage", "d&d")) and _contains_any(body, ("charge", "charges", "payment", "invoice", "confirm")):
        return RuleDecision("INVOICE_QUERY", 0.94, ("detention_or_demurrage", "charge_or_payment_intent"))

    if URL_OR_DOMAIN.search(body) and _contains_any(body, ("payment", "pay now", "customs fee", "customs payment")) and _contains_any(body, ("within 24 hours", "24 hours", "deadline", "urgent", "immediately")):
        return RuleDecision("SPAM", 0.97, ("payment_link", "payment_intent", "deadline"))
    if _contains_any(body, ("bank details", "bank account", "banking information")) and _contains_any(body, ("million", "proposal", "inheritance", "funds")):
        return RuleDecision("SPAM", 0.97, ("financial_details_request", "advance_fee_lure"))
    if PERCENT_OFF.search(body) and _contains_any(body, ("buy now", "limited time", "promotion", "special offer", "discount")):
        return RuleDecision("SPAM", 0.95, ("high_discount", "unsolicited_promotion"))

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
    # A no-attachment request to send a draft BL for checking enters the
    # comparison queue as an already-resolved request; compare.py preserves OK.
    if features.attachment_count == 0 and DRAFT_BL.search(body) and _contains_any(body, checking_terms):
        return RuleDecision("BL_COMPARISON", 0.83, ("draft_bl_request_without_attachment",))

    si_labels = ("pol:", "pod:", "shipper:", "consignee:", "notify party:", "gross wt", "gross weight")
    si_label_count = sum(label in body for label in si_labels)
    if si_label_count >= 3:
        return RuleDecision("SI_REQUEST", 0.93, (f"si_field_labels={si_label_count}",))
    if "shipping instruction" in body and _contains_any(body, ("please find", "please process", "new shipment")):
        return RuleDecision("SI_REQUEST", 0.84, ("shipping_instruction_request",))
    return None
