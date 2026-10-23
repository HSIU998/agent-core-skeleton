"""Zero-LLM keyword extraction for memory lookup.

Pipeline: segment -> merge neighbours -> drop stopwords -> keep words that are
rare in this persona's memories (0 < df < 5%) -> rarest first -> drop words that
contain each other -> at most 5.

Traditional Chinese is converted to Simplified before segmentation when OpenCC
is installed, because the common segmenter dictionary is Simplified; segmenting
Traditional text directly mis-splits words. The original system skipped this
step. Without jieba the module falls back to character bigrams, which is what
the tests use so they run anywhere.
"""
import re

STOPWORDS = {"the", "and", "what", "that", "this", "with", "was", "were", "you", "我們", "什麼", "那個", "這個", "還有"}
RARE_SHARE = 0.05
MAX_KEYS = 5

_CJK = re.compile(r"[一-鿿]")
_TOKEN = re.compile(r"[0-9A-Za-z]+|[一-鿿]+")


def _to_simplified(text: str):
    """Return (simplified_text, converter_used). Same length, so offsets map back."""
    try:
        import opencc
        return opencc.OpenCC("t2s").convert(text), True
    except Exception:
        return text, False


def segment(text: str, use_jieba: bool = True) -> list[str]:
    if use_jieba:
        try:
            import jieba
            jieba.setLogLevel(60)
            simple, converted = _to_simplified(text)
            converted = converted and len(simple) == len(text)
            if not converted:
                simple = text
            out, pos = [], 0
            for piece in jieba.lcut(simple):
                original = text[pos:pos + len(piece)] if converted else piece
                pos += len(piece)
                if _TOKEN.fullmatch(original):
                    out.append(original.lower())
            return out
        except ImportError:
            pass
    out = []
    for run in _TOKEN.findall(text.lower()):
        if _CJK.match(run):
            out.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
        else:
            out.append(run)
    return out


def extract_keywords(text: str, df, total: int, use_jieba: bool = True) -> list[str]:
    """df(word) -> how many memories contain the word; total -> memory count."""
    toks = segment(text, use_jieba)
    cands = set(toks) | {a + b for a, b in zip(toks, toks[1:]) if _CJK.match(a) and _CJK.match(b)}
    cands = [c for c in cands if len(c) >= 2 and c not in STOPWORDS]
    counts = {c: df(c) for c in cands}
    limit = max(1, total) * RARE_SHARE
    rare = sorted((c for c, n in counts.items() if 0 < n < limit), key=lambda c: (counts[c], -len(c)))
    keys: list[str] = []
    for c in rare:
        if not any(c in k or k in c for k in keys):
            keys.append(c)
        if len(keys) == MAX_KEYS:
            break
    return keys
