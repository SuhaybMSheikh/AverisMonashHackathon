"""Create and score source-grounded synthetic SI/BL comparison cases.

This evaluator never calls conversion, classification, or an organizer service. It
uses only existing canonical text and persisted extraction evidence to find clean
base pairs, then runs extraction, normalization, and comparison in a temporary DB.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from backend.app.compare import compare_email
from backend.app.config import PROJECT_ROOT, settings_from_env
from backend.app.db import database, initialize
from backend.app.extract.aliases import FIELDS
from backend.app.extract.pipeline import extract_all


OUTPUT = PROJECT_ROOT / "dev_labels" / "synthetic_cases.json"
REPORT = PROJECT_ROOT / "docs" / "synthetic_report.md"
PORTS = ("SINGAPORE, SINGAPORE", "NANTONG, CHINA", "MERSIN, TURKEY", "CALLAO, PERU")
PARTY = "SYNTHETIC TEST PARTY LTD"


def bases(database_path: Path) -> list[dict]:
    """Find readable, complete pairs whose seven raw SI and BL values are identical."""
    with database(database_path) as con:
        rows = con.execute("""SELECT e.email_id, si.doc_id si_id, bl.doc_id bl_id,
                    si.ext si_ext, bl.ext bl_ext, si.text_path si_text, bl.text_path bl_text
             FROM emails e JOIN documents si ON si.email_id=e.email_id AND si.role_detected='SI'
             JOIN documents bl ON bl.email_id=e.email_id AND bl.role_detected='BL'
             WHERE e.category='BL_COMPARISON' AND si.convert_status!='failed' AND bl.convert_status!='failed'""").fetchall()
        result = []
        for row in rows:
            values, line_numbers = {}, {}
            good = True
            for field in FIELDS:
                si = con.execute("SELECT raw, status, line_no FROM extractions WHERE doc_id=? AND field=?", (row["si_id"], field)).fetchone()
                bl = con.execute("SELECT raw, status, line_no FROM extractions WHERE doc_id=? AND field=?", (row["bl_id"], field)).fetchone()
                if not si or not bl or si["status"] != bl["status"] or si["status"] != "found" or si["raw"] != bl["raw"]:
                    good = False; break
                values[field] = si["raw"]; line_numbers[field] = bl["line_no"]
            if good:
                item = dict(row); item["values"] = values; item["line_numbers"] = line_numbers; item["format"] = f"{row['si_ext'].removeprefix('.')}/{row['bl_ext'].removeprefix('.')}"; result.append(item)
    return result


def replace_field(text: str, line_no: int, new: str) -> str:
    """Replace one parsed label row and its continuation lines, not a duplicate value."""
    lines = text.splitlines(keepends=True)
    index = line_no - 1
    if not 0 <= index < len(lines) or ":" not in lines[index]:
        raise ValueError(f"invalid extracted line number: {line_no}")
    label = lines[index].partition(":")[0]
    # Preserve parser-visible indentation when a noise mutation retains a
    # multiline party/address value.
    lines[index] = f"{label}: {new.replace(chr(10), chr(10) + '  ')}\n"
    while index + 1 < len(lines) and lines[index + 1][:1].isspace():
        del lines[index + 1]
    return "".join(lines)


def typo(value: str) -> str:
    for index, char in enumerate(value):
        if char.isalpha():
            return value[:index] + ("Z" if char.upper() != "Z" else "Y") + value[index + 1:]
    return value + "Z"


def weight_plus_1000(value: str) -> str:
    number = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not number:
        return value + " 1000 KG"
    changed = str(int(float(number.group().replace(",", ""))) + 1000)
    return value[:number.start()] + changed + value[number.end():]


def weight_swap(value: str) -> str:
    digits = [index for index, char in enumerate(value) if char.isdigit()]
    if len(digits) >= 2:
        first, second = digits[0], digits[1]
        chars = list(value); chars[first], chars[second] = chars[second], chars[first]
        if "".join(chars) != value: return "".join(chars)
    return weight_plus_1000(value)


def count_change(value: str, delta: int) -> str:
    match = re.search(r"\d+", value)
    if not match: return "1 " + value
    number = max(0, int(match.group()) + delta)
    return value[:match.start()] + str(number) + value[match.end():]


def port_change(value: str) -> str:
    return next(port for port in PORTS if port.upper() not in value.upper())


def mutations(values: dict[str, str]) -> list[tuple[str, dict[str, str], set[str]]]:
    """Return mutation name, BL replacements, and exact expected defect fields."""
    result = []
    count = values["container_count"]
    result += [("defect_container_plus_one", {"container_count": count_change(count, 1)}, {"container_count"}),
               ("defect_container_minus_one", {"container_count": count_change(count, -1)}, {"container_count"})]
    weight = values["gross_weight_kg"]
    result += [("defect_weight_digit_swap", {"gross_weight_kg": weight_swap(weight)}, {"gross_weight_kg"}),
               ("defect_weight_plus_1000", {"gross_weight_kg": weight_plus_1000(weight)}, {"gross_weight_kg"})]
    for field in ("shipper", "consignee", "notify_party"):
        result += [(f"defect_{field}_typo", {field: typo(values[field])}, {field}),
                   (f"defect_{field}_different_party", {field: PARTY}, {field})]
    for field in ("port_of_loading", "port_of_discharge"):
        result.append((f"defect_{field}_different_port", {field: port_change(values[field])}, {field}))
    result += [("defect_container_and_weight", {"container_count": count_change(count, 1), "gross_weight_kg": weight_plus_1000(weight)}, {"container_count", "gross_weight_kg"}),
               ("defect_shipper_and_loading_port", {"shipper": typo(values["shipper"]), "port_of_loading": port_change(values["port_of_loading"])}, {"shipper", "port_of_loading"})]
    party = values["shipper"]
    punctuated = _punctuation_variant(party)
    result += [("noise_case", {"shipper": party.swapcase()}, set()),
               ("noise_extra_spaces", {"consignee": re.sub(r"\s+", "   ", values["consignee"])}, set()),
               ("noise_punctuation", {"shipper": punctuated}, set()),
               ("noise_thousands_separator", {"gross_weight_kg": _comma_weight(weight)}, set()),
               ("noise_kg_kgs", {"gross_weight_kg": _kg_variant(weight)}, set()),
               ("noise_unlocode", {"port_of_loading": _code_variant(values["port_of_loading"])}, set()),
               ("noise_address_separator", {"notify_party": values["notify_party"].replace("\n", " | ")}, set())]
    return [(name, changes, expected) for name, changes, expected in result if all(values[key] != value for key, value in changes.items())]


def _comma_weight(value: str) -> str:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", value)
    if not match: return value + ",000"
    raw = match.group().replace(",", "")
    changed = f"{int(float(raw)):,}" if "." not in raw else raw
    return value[:match.start()] + changed + value[match.end():]


def _punctuation_variant(value: str) -> str:
    if re.search(r"\bSDN\s+BHD\b", value, re.I):
        return re.sub(r"\bSDN\s+BHD\b", "SDN. BHD.", value, count=1, flags=re.I)
    return re.sub(r"\s+", ". ", value, count=1)


def _kg_variant(value: str) -> str:
    if re.search(r"\bKGS\b", value, re.I): return re.sub(r"\bKGS\b", "KG", value, flags=re.I)
    if re.search(r"\bKG\b", value, re.I): return re.sub(r"\bKG\b", "KGS", value, flags=re.I)
    return value + " KGS"


def _code_variant(value: str) -> str:
    return re.sub(r"\s*\([A-Z]{2}[A-Z0-9]{3}\)\s*$", "", value, flags=re.I) if re.search(r"\([A-Z]{2}[A-Z0-9]{3}\)\s*$", value, re.I) else value + " (SGSIN)"


class SyntheticRunner:
    """Reuse one throwaway DB while exercising only extraction and comparison."""
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = settings_from_env({"DATABASE_PATH": root / "synthetic.sqlite3", "DERIVED_DIR": root / "derived"})
        text_dir = self.settings.derived_dir / "text"; meta_dir = self.settings.derived_dir / "meta"; text_dir.mkdir(parents=True); meta_dir.mkdir()
        for role in ("si", "bl"):
            (meta_dir / f"{role}.json").write_text(json.dumps({"confidence": 1.0}), encoding="utf-8")
        initialize(self.settings.database_path)
        with database(self.settings.database_path) as con:
            con.execute("INSERT INTO emails (email_id,from_addr,subject,body,category) VALUES ('synthetic','source@example.test','','','BL_COMPARISON')")
            for role in ("si", "bl"):
                con.execute("INSERT INTO documents (doc_id,email_id,path,ext,size,sha256,role_detected,convert_status,text_path,meta_path) VALUES (?, 'synthetic', ?, '.txt', 1, 'synthetic', ?, 'ok', ?, ?)", (role, f"attachments/{role}.txt", role.upper(), f"text/{role}.txt", f"meta/{role}.json"))

    def run(self, base: dict, si_text: str, bl_text: str) -> dict:
        text_dir = self.settings.derived_dir / "text"
        (text_dir / "si.txt").write_text(si_text, encoding="utf-8"); (text_dir / "bl.txt").write_text(bl_text, encoding="utf-8")
        with database(self.settings.database_path) as con:
            con.execute("UPDATE documents SET ext=? WHERE doc_id='si'", (base["si_ext"],))
            con.execute("UPDATE documents SET ext=? WHERE doc_id='bl'", (base["bl_ext"],))
        extract_all(self.settings, {"si", "bl"})
        return compare_email(self.settings, "synthetic")

    def close(self): self.temp.cleanup()


def evaluate_case(runner: SyntheticRunner, base: dict, si_text: str, bl_text: str, name: str, expected: set[str]) -> dict:
    result = runner.run(base, si_text, bl_text)
    actual = set(result["defect_fields"])
    raw = {item["field"]: {"si": item["si_raw"], "bl": item["bl_raw"]} for item in result["field_results"] if item["field"] in expected | actual}
    return {"base_email_id": base["email_id"], "source_format": base["format"], "mutation": name, "expected_status": "MISMATCH" if expected else "OK", "expected_defect_fields": sorted(expected), "actual_status": result["status"], "actual_defect_fields": sorted(actual), "passed": result["status"] == ("MISMATCH" if expected else "OK") and actual == expected, "raw_values": raw}


def report(cases: list[dict], base_counts: Counter[str]) -> str:
    defect = Counter(); noise = Counter(); by_format = defaultdict(lambda: Counter())
    failures = []
    for case in cases:
        expected, actual = set(case["expected_defect_fields"]), set(case["actual_defect_fields"])
        defect["tp"] += len(expected & actual); defect["fp"] += len(actual - expected); defect["fn"] += len(expected - actual)
        bucket = by_format[case["source_format"]]; bucket["cases"] += 1; bucket["passed"] += case["passed"]
        if not expected: noise["total"] += 1; noise["false_alarm"] += case["actual_status"] != "OK"
        if not case["passed"]: failures.append(case)
    precision = defect["tp"] / (defect["tp"] + defect["fp"]) if defect["tp"] + defect["fp"] else 0.0
    recall = defect["tp"] / (defect["tp"] + defect["fn"]) if defect["tp"] + defect["fn"] else 0.0
    lines = ["# Synthetic comparison evaluation", "", "This report uses source-derived identical raw-value pairs and isolated temporary databases; no organizer data or submission was used.", "", "## Base pairs by source format", "", "| Format | Pairs |", "| --- | ---: |", *[f"| {fmt} | {count} |" for fmt, count in sorted(base_counts.items())], "", "## Aggregate", "", f"- Per-field defect precision: {precision:.4f}", f"- Per-field defect recall: {recall:.4f}", f"- Noise false-alarm rate: {noise['false_alarm'] / noise['total'] if noise['total'] else 0.0:.4f} ({noise['false_alarm']}/{noise['total']})", "", "## Results by source format", "", "| Format | Cases | Passed |", "| --- | ---: | ---: |", *[f"| {fmt} | {value['cases']} | {value['passed']} |" for fmt, value in sorted(by_format.items())], "", "## Failing cases", ""]
    if not failures: lines.append("No failing cases.")
    for case in failures:
        lines += [f"### {case['base_email_id']} — {case['mutation']}", "", f"Expected `{case['expected_status']}` with `{case['expected_defect_fields']}`; got `{case['actual_status']}` with `{case['actual_defect_fields']}`.", "", "| Field | SI raw | Mutated BL raw |", "| --- | --- | --- |", *[f"| {field} | {value['si']} | {value['bl']} |" for field, value in case["raw_values"].items()], ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    settings = settings_from_env()
    # Populate the source-side evidence from already-converted canonical text.
    # Deliberately do not invoke conversion or classification here.
    extract_all(settings)
    base_pairs = bases(settings.database_path); counts = Counter(pair["format"] for pair in base_pairs)
    cases = []; runner = SyntheticRunner()
    try:
        for base in base_pairs:
            si = (settings.derived_dir / base["si_text"]).read_text(encoding="utf-8"); bl = (settings.derived_dir / base["bl_text"]).read_text(encoding="utf-8")
            for name, changes, expected in mutations(base["values"]):
                changed = bl
                for field, value in changes.items(): changed = replace_field(changed, base["line_numbers"][field], value)
                cases.append(evaluate_case(runner, base, si, changed, name, expected))
    finally:
        runner.close()
    OUTPUT.write_text(json.dumps({"base_pairs_by_format": dict(sorted(counts.items())), "cases": cases}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT.write_text(report(cases, counts), encoding="utf-8")
    print(f"base pairs: {len(base_pairs)}; cases: {len(cases)}; outputs: {OUTPUT}, {REPORT}")


if __name__ == "__main__": main()
