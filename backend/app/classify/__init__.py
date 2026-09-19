"""Explainable, rules-first email categorisation."""

from .pipeline import ClassificationRun, classify_all

__all__ = ["ClassificationRun", "classify_all"]
