# -*- coding: utf-8 -*-
"""Closure check: every change in the ledger must carry its final goal, what is
measured, the pass line, a result in one of five categories, and evidence.

Why: a batch of fixes can pass every mechanism check ("the code ran") while
nobody can say whether the goal was reached. The ledger forces the question
before the change is made, and this check refuses to let "the code ran" be
booked as "fixed".

Rules (red blocks the release; yellow must be fixed before the next batch):
  R1  missing column (id / goal / measure / threshold / result)
  R2  result not one of: passed, observing, partial, failed, untouched
  R3  result given without evidence (untouched needs none)
  R4  booked as passed but goal_measured is false  -> mechanism only, not a fix
  R5  booked as passed while mechanism_ok is false
  Y1  observing without a since date

Usage:  python -m verification.closure_check path/to/ledger.json
Exit code 1 when any red finding exists.
"""
import json
import sys
from collections import Counter
from dataclasses import dataclass

RESULTS = ("passed", "observing", "partial", "failed", "untouched")
REQUIRED = ("id", "goal", "measure", "threshold", "result")


@dataclass(frozen=True)
class Finding:
    entry_id: str
    level: str  # "red" or "yellow"
    rule: str
    text: str


def _blank(value) -> bool:
    return value is None or str(value).strip() == ""


def check_entry(entry: dict) -> list:
    eid = str(entry.get("id") or "?")
    out = []
    for col in REQUIRED:
        if _blank(entry.get(col)):
            out.append(Finding(eid, "red", "R1", f"missing column: {col}"))
    result = entry.get("result")
    if not _blank(result) and result not in RESULTS:
        out.append(Finding(eid, "red", "R2", f"unknown result {result!r}; expected one of {', '.join(RESULTS)}"))
    if result in RESULTS and result != "untouched" and _blank(entry.get("evidence")):
        out.append(Finding(eid, "red", "R3", f"result {result!r} without evidence"))
    if result == "passed" and not entry.get("goal_measured", False):
        out.append(Finding(eid, "red", "R4", "booked as passed but the goal was never measured (mechanism only)"))
    if result == "passed" and entry.get("mechanism_ok") is False:
        out.append(Finding(eid, "red", "R5", "booked as passed while the mechanism check failed"))
    if result == "observing" and _blank(entry.get("since")):
        out.append(Finding(eid, "yellow", "Y1", "observing without a since date"))
    return out


@dataclass
class Report:
    findings: list
    by_result: Counter
    entries: int

    @property
    def red(self) -> list:
        return [f for f in self.findings if f.level == "red"]

    @property
    def yellow(self) -> list:
        return [f for f in self.findings if f.level == "yellow"]

    @property
    def ok(self) -> bool:
        return not self.red


def check(entries: list) -> Report:
    findings = []
    for entry in entries:
        findings.extend(check_entry(entry))
    by_result = Counter(str(e.get("result") or "?") for e in entries)
    return Report(findings, by_result, len(entries))


def mechanism_only_check(entries: list) -> bool:
    """The check this repo replaced: green when every change reports that its code ran.
    Kept as the counterexample (see tests)."""
    return all(e.get("mechanism_ok", False) for e in entries)


def render(report: Report) -> str:
    lines = [f"ledger: {report.entries} entries"]
    lines.append("by result: " + ", ".join(f"{k} {v}" for k, v in sorted(report.by_result.items())))
    for level, items in (("RED", report.red), ("YELLOW", report.yellow)):
        lines.append(f"{level}: {len(items)}")
        for f in items:
            lines.append(f"  [{f.rule}] {f.entry_id}: {f.text}")
    lines.append("verdict: " + ("closed, release allowed" if report.ok else "not closed, release blocked"))
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        entries = json.load(fh)
    report = check(entries)
    print(render(report))
    return 1 if report.red else 0


if __name__ == "__main__":
    sys.exit(main())
