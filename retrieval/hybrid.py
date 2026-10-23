"""Hybrid ranking: semantic similarity x time decay + keyword (BM25), then MMR.

`semantic` here is cosine similarity over character bigrams so the demo runs
without an embedding model; the original system uses a shared embedding
service. The weights are plain parameters on purpose: the original system tuned
them by hand, and a fixed similarity threshold could not separate right answers
from wrong ones. Tune them against a labelled question set, not by feel.
"""
import math
from collections import Counter

HALF_LIFE_DAYS = 30.0


def _bigrams(text: str) -> Counter:
    t = "".join(ch for ch in text.lower() if not ch.isspace())
    return Counter(t[i:i + 2] for i in range(len(t) - 1)) or Counter({t: 1})


def cosine(a: str, b: str) -> float:
    va, vb = _bigrams(a), _bigrams(b)
    dot = sum(va[k] * vb[k] for k in va)
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    return dot / (na * nb) if na and nb else 0.0


def rank(query: str, memories: list[dict], bm25: dict[int, float], now: float,
         w_sem: float = 0.6, w_kw: float = 0.4, limit: int = 3, mmr_lambda: float = 0.7) -> list[dict]:
    """memories: [{"id", "text", "ts"}]. bm25: id -> keyword score (may be missing)."""
    top_kw = max(bm25.values(), default=0.0) or 1.0
    scored = []
    for m in memories:
        decay = math.pow(0.5, max(0.0, now - m["ts"]) / 86400 / HALF_LIFE_DAYS)
        rel = w_sem * cosine(query, m["text"]) + w_kw * (bm25.get(m["id"], 0.0) / top_kw)
        if rel > 0:
            scored.append({**m, "score": rel * (0.5 + 0.5 * decay)})
    return mmr(scored, limit, mmr_lambda)


def mmr(scored: list[dict], limit: int, lam: float) -> list[dict]:
    """Maximal Marginal Relevance: each pick trades relevance against similarity
    to what is already picked, so the top slots are not the same event twice."""
    picked: list[dict] = []
    pool = sorted(scored, key=lambda m: m["score"], reverse=True)
    while pool and len(picked) < limit:
        best = max(pool, key=lambda m: lam * m["score"]
                   - (1 - lam) * max((cosine(m["text"], p["text"]) for p in picked), default=0.0))
        picked.append(best)
        pool.remove(best)
    return picked
