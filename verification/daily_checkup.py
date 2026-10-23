# -*- coding: utf-8 -*-
"""Daily checkup (read-only): read today's log, compare it with yesterday's
baseline and the list of known problems, and put only what is NEW or WORSE at
the top. Known problems stay listed below. A known problem that did not show
up today is suggested for removal from the list; if it comes back, it returns
to the top by itself.

Why: a light that is red every day gets looked past. "New or worse first"
keeps the one new red light visible among eleven old ones.

Usage:
  python -m verification.daily_checkup today.log [--known known.json] [--baseline baseline.json]

known.json:    [{"pattern": "^fallback:embedding", "name": "...", "since": "YYYY-MM-DD"}, ...]
baseline.json: {"<signature>": <count yesterday>, ...}
This module never writes a file.
"""
import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass

RULES = (
    ("fallback", re.compile(r"\b(fallback|fell back|degraded)\b", re.I)),
    ("error", re.compile(r"\bERROR\b|Traceback")),
    ("skipped", re.compile(r"\bSKIPPED\b")),
    ("timeout", re.compile(r"\btimed? ?out\b", re.I)),
)
_MODULE = re.compile(r"\[([^\]\s]+)\]")
WORSE_FACTOR = 2.0
ORDER = {"new": 0, "worse": 1, "known": 2, "fixed": 3}


def signature(line: str):
    """'<rule>:<module>' for a line that matches a rule, else None."""
    for name, pat in RULES:
        if pat.search(line):
            m = _MODULE.search(line)
            return f"{name}:{m.group(1) if m else '-'}"
    return None


def extract(lines) -> Counter:
    counts = Counter()
    for line in lines:
        sig = signature(line)
        if sig:
            counts[sig] += 1
    return counts


@dataclass
class Item:
    signature: str
    today: int
    baseline: int
    status: str  # new / worse / known / fixed
    name: str = ""


@dataclass
class Report:
    items: list

    def section(self, status: str) -> list:
        return [i for i in self.items if i.status == status]

    @property
    def to_look_at(self) -> list:
        return [i for i in self.items if i.status in ("new", "worse")]


def classify(today: Counter, baseline: dict, known: list) -> Report:
    def known_entry(sig):
        for k in known:
            if re.match(k["pattern"], sig):
                return k
        return None

    items, matched = [], set()
    for sig, n in today.items():
        k = known_entry(sig)
        b = int(baseline.get(sig, 0))
        if k is None:
            status = "new"
        else:
            matched.add(k["pattern"])
            status = "worse" if b > 0 and n > b * WORSE_FACTOR else "known"
        items.append(Item(sig, n, b, status, (k or {}).get("name", "")))
    for k in known:
        if k["pattern"] not in matched:
            items.append(Item(k["pattern"], 0, 0, "fixed", k.get("name", "")))
    items.sort(key=lambda i: (ORDER[i.status], -i.today, i.signature))
    return Report(items)


def naive_report(today: Counter) -> list:
    """The report this repo replaced: every signature, sorted by count, no memory of
    yesterday and no known list. Kept as the counterexample (see tests)."""
    return [sig for sig, _ in sorted(today.items(), key=lambda kv: (-kv[1], kv[0]))]


def render(report: Report) -> str:
    out = ["## look at these (new or worse)"]
    look = report.to_look_at
    out += [f"- {i.status.upper():5} {i.signature}  today {i.today}, yesterday {i.baseline}" for i in look] or ["- (none)"]
    out.append("## known, unchanged")
    out += [f"- {i.signature}  today {i.today}, yesterday {i.baseline}  ({i.name})" for i in report.section("known")] or ["- (none)"]
    out.append("## not seen today (drop from known if it stays away)")
    out += [f"- {i.signature}  ({i.name})" for i in report.section("fixed")] or ["- (none)"]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="read-only daily checkup")
    ap.add_argument("log")
    ap.add_argument("--known", default=None)
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args(argv)
    with open(args.log, encoding="utf-8") as fh:
        today = extract(fh)
    known, baseline = [], {}
    if args.known:
        with open(args.known, encoding="utf-8") as fh:
            known = json.load(fh)
    if args.baseline:
        with open(args.baseline, encoding="utf-8") as fh:
            baseline = json.load(fh)
    print(render(classify(today, baseline, known)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
