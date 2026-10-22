"""Write gate for core identity fields: every write ends as allow, deny or degrade."""
import time

CORE_FIELDS = {"name", "persona_id"}          # never rewritten after creation
GUARDED_FIELDS = {"self_description"}         # rewritten only as an appended note


class CoreGuard:
    def __init__(self):
        self.audit: list[dict] = []

    def write(self, core: dict, field_name: str, value: str, source: str) -> str:
        if field_name in CORE_FIELDS and field_name in core:
            verdict = "deny"
        elif field_name in GUARDED_FIELDS and field_name in core:
            core.setdefault("notes", []).append({"field": field_name, "value": value, "source": source})
            verdict = "degrade"
        else:
            core[field_name] = value
            verdict = "allow"
        self.audit.append({"ts": time.time(), "field": field_name, "source": source, "verdict": verdict})
        return verdict
