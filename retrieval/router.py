"""Decide whether this turn needs memory or the web.

A model classifier is tried first. If it raises or returns something that is not
the expected JSON, fall back to rules instead of answering "no lookup needed".
The original system returned all-False on failure, so a flaky model silently
switched memory lookup off.
"""
import json

MEMORY_CUES = ("記得", "上次", "以前", "那次", "之前", "remember", "last time", "before")
WEB_CUES = ("最新", "新聞", "查一下", "上網", "搜尋", "price", "latest", "news", "search")


def rule_route(text: str) -> dict:
    t = text.lower()
    return {"use_memory": any(c in t for c in MEMORY_CUES),
            "use_web": any(c in t for c in WEB_CUES),
            "source": "rules"}


def route(text: str, classify=None) -> dict:
    """classify(text) -> JSON string with use_memory / use_web booleans."""
    if classify is not None:
        try:
            data = json.loads(classify(text))
            if isinstance(data.get("use_memory"), bool) and isinstance(data.get("use_web"), bool):
                return {"use_memory": data["use_memory"], "use_web": data["use_web"], "source": "model"}
            reason = "bad_shape"
        except Exception as exc:
            reason = type(exc).__name__
        return {**rule_route(text), "source": f"rules_after_{reason}"}
    return rule_route(text)
