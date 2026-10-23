# -*- coding: utf-8 -*-
"""Canary: before trusting a reviewer (a model, a script, a person), seed known
errors into a piece of code and measure two things: how many of the seeded
errors the reviewer catches, and how many clean lines it flags anyway.

A reviewer that says "looks good" to everything scores recall 0. A reviewer
that flags every line scores recall 1 and is just as useless; only the
false-alarm measurement exposes it. Both numbers must clear their lines before
a verdict from that reviewer is used for anything.

Reviewer protocol: a callable that takes source text and returns the set of
1-based line numbers it considers wrong.
"""
import random
import re
from dataclasses import dataclass
from typing import Callable

Reviewer = Callable[[str], set]

# (name, pattern, replacement) - one edit per chosen line
OPERATORS = (
    ("flip_ge", re.compile(r">="), ">"),
    ("flip_le", re.compile(r"<="), "<"),
    ("flip_eq", re.compile(r"=="), "!="),
    ("drop_not", re.compile(r"\bnot "), ""),
    ("true_to_false", re.compile(r"\bTrue\b"), "False"),
    ("off_by_one", re.compile(r"(?<![\w.])(\d+)(?![\w.])"), lambda m: str(int(m.group(1)) + 1)),
)


@dataclass(frozen=True)
class Mutation:
    line: int
    operator: str
    before: str
    after: str


def candidates(source: str) -> list:
    """(line_no, operator) for every non-comment line where some operator applies."""
    out = []
    for i, text in enumerate(source.splitlines(), 1):
        if text.lstrip().startswith("#"):
            continue
        for name, pat, _ in OPERATORS:
            if pat.search(text):
                out.append((i, name))
                break
    return out


def seed(source: str, n: int, rng_seed: int = 0) -> tuple:
    """Return (mutated source, list of Mutation). Deterministic for a given rng_seed."""
    lines = source.splitlines()
    pool = candidates(source)
    if n > len(pool):
        raise ValueError(f"asked for {n} mutations but only {len(pool)} lines are mutable")
    rng = random.Random(rng_seed)
    chosen = sorted(rng.sample(pool, n))
    muts = []
    for line_no, op_name in chosen:
        pat, repl = next((p, r) for name, p, r in OPERATORS if name == op_name)
        before = lines[line_no - 1]
        after = pat.sub(repl, before, count=1)
        lines[line_no - 1] = after
        muts.append(Mutation(line_no, op_name, before, after))
    return "\n".join(lines) + ("\n" if source.endswith("\n") else ""), muts


@dataclass
class Score:
    seeded: int
    caught: int
    missed: list
    false_alarms: int
    clean_lines: int
    min_recall: float
    max_false_alarm_rate: float

    @property
    def recall(self) -> float:
        return self.caught / self.seeded if self.seeded else 0.0

    @property
    def false_alarm_rate(self) -> float:
        return self.false_alarms / self.clean_lines if self.clean_lines else 0.0

    @property
    def trusted(self) -> bool:
        return self.recall >= self.min_recall and self.false_alarm_rate <= self.max_false_alarm_rate

    def __str__(self) -> str:
        return (f"recall {self.caught}/{self.seeded} = {self.recall:.2f}, "
                f"false alarms {self.false_alarms}/{self.clean_lines} = {self.false_alarm_rate:.2f}, "
                f"trusted = {self.trusted}")


def score(mutations: list, flagged_on_mutated: set, flagged_on_clean: set, clean_line_count: int,
          min_recall: float = 0.75, max_false_alarm_rate: float = 0.1) -> Score:
    seeded_lines = {m.line for m in mutations}
    caught = seeded_lines & set(flagged_on_mutated)
    return Score(
        seeded=len(seeded_lines),
        caught=len(caught),
        missed=sorted(seeded_lines - caught),
        false_alarms=len(set(flagged_on_clean)),
        clean_lines=clean_line_count,
        min_recall=min_recall,
        max_false_alarm_rate=max_false_alarm_rate,
    )


def recall_only_score(mutations: list, flagged_on_mutated: set) -> float:
    """The measurement this repo replaced: recall alone, no look at the clean copy.
    Kept as the counterexample (see tests)."""
    seeded_lines = {m.line for m in mutations}
    return len(seeded_lines & set(flagged_on_mutated)) / len(seeded_lines) if seeded_lines else 0.0


def run(source: str, reviewer: Reviewer, n: int = 4, rng_seed: int = 0, **limits) -> tuple:
    """Seed n errors, show the reviewer both copies, return (Score, mutations)."""
    mutated, muts = seed(source, n, rng_seed)
    on_mutated = reviewer(mutated)
    on_clean = reviewer(source)
    return score(muts, on_mutated, on_clean, len(source.splitlines()), **limits), muts
