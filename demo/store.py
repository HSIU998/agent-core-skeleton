"""SQLite memory store with a deterministic hybrid recall.

Relevance here is plain character-bigram overlap so the demo runs without an
embedding model; the real system uses a shared embedding service. The ranking
shape is the same: relevance x time decay, then near-duplicates move to the back.
"""
import math
import sqlite3
import time

HALF_LIFE_DAYS = 30.0
DUP_COVERAGE = 0.7  # coverage, not Jaccard: a short line contained in a long one is a duplicate


def _grams(text: str) -> set:
    t = "".join(ch for ch in text.lower() if not ch.isspace())
    return {t[i:i + 2] for i in range(len(t) - 1)} or {t}


class MemoryStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            " id INTEGER PRIMARY KEY, persona TEXT, text TEXT, ts REAL)"
        )
        # The running dialogue is kept apart from memories. Writing each turn back
        # into the recall pool lets the last thing said outrank what actually happened.
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS dialogue ("
            " id INTEGER PRIMARY KEY, persona TEXT, role TEXT, text TEXT, ts REAL)"
        )

    def log_dialogue(self, persona: str, role: str, text: str) -> None:
        self.db.execute(
            "INSERT INTO dialogue (persona, role, text, ts) VALUES (?, ?, ?, ?)",
            (persona, role, text, time.time()),
        )
        self.db.commit()

    def add(self, persona: str, text: str, ts: float | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO memories (persona, text, ts) VALUES (?, ?, ?)",
            (persona, text, time.time() if ts is None else ts),
        )
        self.db.commit()
        return cur.lastrowid

    def count(self, persona: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM memories WHERE persona = ?", (persona,)
        ).fetchone()[0]

    def recall(self, persona: str, query: str, limit: int = 3, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        q = _grams(query)
        scored = []
        for mid, text, ts in self.db.execute(
            "SELECT id, text, ts FROM memories WHERE persona = ?", (persona,)
        ):
            g = _grams(text)
            relevance = len(q & g) / len(q)
            if relevance == 0:
                continue
            age_days = max(0.0, now - ts) / 86400
            decay = math.pow(0.5, age_days / HALF_LIFE_DAYS)
            scored.append({"id": mid, "text": text, "score": relevance * (0.5 + 0.5 * decay), "_g": g})
        scored.sort(key=lambda m: m["score"], reverse=True)

        keep, dup, seen = [], [], []
        for m in scored:
            g = m.pop("_g")
            if any(len(g & s) / min(len(g), len(s)) >= DUP_COVERAGE for s in seen):
                dup.append(m)  # not dropped, only moved back
            else:
                keep.append(m)
                seen.append(g)
        return (keep + dup)[:limit]
