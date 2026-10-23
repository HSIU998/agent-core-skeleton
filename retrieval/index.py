"""Keyword index with SQLite FTS5 and BM25 ranking.

The original system counted keyword hits with `instr(content, ?)` over the whole
memory table: every query is a full scan, and ranking is only "how rare is the
word". FTS5 keeps an inverted index and ranks with BM25 (term frequency,
inverse document frequency, length normalisation) in one query.

FTS5's default tokenizer does not split Chinese, so text is stored as
space-separated tokens from `keywords.segment`.
"""
import sqlite3

from .keywords import segment


class KeywordIndex:
    def __init__(self, path: str = ":memory:", use_jieba: bool = True):
        self.use_jieba = use_jieba
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem USING fts5(persona UNINDEXED, mid UNINDEXED, tokens)")

    def _tokens(self, text: str) -> str:
        return " ".join(segment(text, self.use_jieba))

    def add(self, persona: str, mid: int, text: str) -> None:
        self.db.execute("INSERT INTO mem (persona, mid, tokens) VALUES (?, ?, ?)", (persona, mid, self._tokens(text)))
        self.db.commit()

    def df(self, persona: str, token: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM mem WHERE mem MATCH ? AND persona = ?", (f'"{token}"', persona)
        ).fetchone()[0]

    def count(self, persona: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM mem WHERE persona = ?", (persona,)).fetchone()[0]

    def search(self, persona: str, query: str, limit: int = 10) -> list[tuple[int, float]]:
        """Return (memory id, score) pairs, best first. Higher score = better match."""
        toks = sorted(set(self._tokens(query).split()))
        if not toks:
            return []
        match = " OR ".join(f'"{t}"' for t in toks)
        rows = self.db.execute(
            "SELECT mid, bm25(mem) FROM mem WHERE mem MATCH ? AND persona = ? ORDER BY bm25(mem) LIMIT ?",
            (match, persona, limit),
        ).fetchall()
        return [(int(mid), -score) for mid, score in rows]  # bm25() is lower-is-better
