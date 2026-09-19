"""Parse canonical text without interpreting the values it contains."""
from __future__ import annotations

from dataclasses import dataclass
import re


_UNSEPARATED_CONSIGNEE = re.compile(r"^(?P<label>consignee(?:\s*\([^)]*\))?)\s+(?P<value>\S.+)$", re.I)


@dataclass(frozen=True)
class LabelValue:
    label: str
    value: str
    line_no: int
    continuation: tuple[str, ...] = ()

    @property
    def raw(self) -> str:
        return "\n".join((self.value, *self.continuation)).strip()


def parse(text: str) -> list[LabelValue]:
    """Return ordered label/value entries, folding indented lines into their owner.

    Canonical headings and separator lines are intentionally not entries. A colon is
    required so prose such as a PDF layout artefact remains display-only text.
    """
    entries: list[LabelValue] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line[:1].isspace() and entries:
            previous = entries[-1]
            entries[-1] = LabelValue(previous.label, previous.value, previous.line_no, (*previous.continuation, line.strip()))
            continue
        label, separator, value = line.partition(":")
        if separator and label.strip() and set(line.strip()) != {"="}:
            entries.append(LabelValue(label.strip(), value.strip(), line_no))
            continue
        # Some text-layer PDFs lose the colon after a two-column field label.
        # Recognize only the observed, unambiguous consignee form; all other
        # unlabelled lines remain display-only text.
        match = _UNSEPARATED_CONSIGNEE.match(line.strip())
        if match:
            entries.append(LabelValue(match.group("label"), match.group("value"), line_no))
    return entries
