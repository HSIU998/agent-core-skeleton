"""Drive values that live in the core, not in the model.

Two rules came from a real failure: satisfying a drive used to subtract a fixed
amount with a floor of 0, and one busy day ground every drive to zero.
Now growth is capped at 8 hours per update and satisfying is multiplicative,
so a drive can approach the floor but never reach zero.
"""
from dataclasses import dataclass, field

MAX_GROW_HOURS = 8.0
FLOOR = 0.02


@dataclass
class DriveState:
    rates: dict = field(default_factory=lambda: {"rest": 0.03, "talk": 0.05, "explore": 0.02})
    values: dict = field(default_factory=lambda: {"rest": 0.3, "talk": 0.3, "explore": 0.3})

    def grow(self, hours: float) -> None:
        h = min(hours, MAX_GROW_HOURS)
        for k, r in self.rates.items():
            self.values[k] = min(1.0, max(FLOOR, self.values[k] + r * h))

    def satisfy(self, name: str, keep: float = 0.6) -> None:
        self.values[name] = max(FLOOR, self.values[name] * keep)
