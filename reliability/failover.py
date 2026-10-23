"""Model call failover: primary -> backup from a different provider -> local.

Two rules came from real outages:
- A backup on the same provider and quota as the primary is not a backup. When
  the cloud quota ran out, every model went silent together. The original
  system's backup was literally the same model name as the primary, and the
  local last resort was commented out.
- Every fallback is counted and reported, so running on the backup for a month
  shows up as a number instead of passing unnoticed.
"""
from dataclasses import dataclass, field


@dataclass
class Backend:
    name: str
    provider: str          # who can take it away from you: vendor / quota / machine
    call: object           # callable(prompt) -> str


class AllBackendsFailed(RuntimeError):
    pass


@dataclass
class FailoverChain:
    backends: list
    used: dict = field(default_factory=dict)
    failures: dict = field(default_factory=dict)

    def problems(self) -> list[str]:
        """Configuration smells worth refusing to start with."""
        out = []
        names = [b.name for b in self.backends]
        if len(set(names)) < len(names):
            out.append("duplicate backend: a backup equal to the primary adds nothing")
        if len({b.provider for b in self.backends}) < 2:
            out.append("single provider: one quota or outage stops every backend")
        return out

    def complete(self, prompt: str) -> tuple[str, str]:
        """Return (text, backend name). Raises AllBackendsFailed with every reason."""
        reasons = []
        for b in self.backends:
            try:
                text = b.call(prompt)
                self.used[b.name] = self.used.get(b.name, 0) + 1
                return text, b.name
            except Exception as exc:
                self.failures[b.name] = self.failures.get(b.name, 0) + 1
                reasons.append(f"{b.name}: {type(exc).__name__}: {exc}")
        raise AllBackendsFailed("; ".join(reasons))
