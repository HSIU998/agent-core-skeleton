"""Parse model JSON without inventing values.

The pattern this replaces: when the model's answer could not be parsed, fill in
neutral defaults (mood "neutral", brightness 0.5, ...) and pass them on. The
next stage cannot tell a real 0.5 from "we did not understand the answer", so a
broken model looks like a calm one. Here a failure stays a failure.
"""
import json
from dataclasses import dataclass


@dataclass
class Parsed:
    ok: bool
    data: dict
    error: str = ""


def parse_fields(raw: str, required: dict) -> Parsed:
    """required: field -> type. Missing or wrong-typed fields fail the parse."""
    text = raw if isinstance(raw, str) else str(raw)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return Parsed(False, {}, "no JSON object in model output")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        return Parsed(False, {}, f"invalid JSON: {exc.msg}")
    missing = [k for k, t in required.items() if not isinstance(data.get(k), t)]
    if missing:
        return Parsed(False, {}, "missing or wrong type: " + ", ".join(missing))
    return Parsed(True, {k: data[k] for k in required})


def parse_with_defaults(raw: str, defaults: dict) -> dict:
    """The silent pattern, kept only so the tests can show what it hides."""
    try:
        data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return {k: data.get(k, v) for k, v in defaults.items()}
    except Exception:
        return dict(defaults)
