"""Alarm center: one active row per (code, module, fingerprint), counted.

- Repeats update the existing row instead of adding a new one, so a recurring
  fault reads as "x37, chronic" rather than 37 lines nobody reads.
- `agent_facing` defaults to False. Once, a monitoring disconnect was fed to an
  agent as its own body feeling, and it invented an illness to explain it.
  Forgetting the flag means "not pushed", which is the safe side.
"""
import time

CHRONIC_COUNT = 5


class AlarmCenter:
    def __init__(self):
        self.rows: list[dict] = []

    def trigger(self, code: str, module: str, description: str,
                fingerprint: str = "", agent_facing: bool = False) -> dict:
        now = time.time()
        for row in self.rows:
            if row["status"] == "active" and (row["code"], row["module"], row["fingerprint"]) == (code, module, fingerprint):
                row["count"] += 1
                row["last_seen"] = now
                row["description"] = description
                row["chronic"] = row["count"] >= CHRONIC_COUNT
                return row
        row = {"code": code, "module": module, "fingerprint": fingerprint, "description": description,
               "count": 1, "first_seen": now, "last_seen": now, "chronic": False,
               "status": "active", "agent_facing": agent_facing}
        self.rows.append(row)
        return row

    def resolve(self, code: str, module: str, fingerprint: str = "") -> int:
        n = 0
        for row in self.rows:
            if row["status"] == "active" and (row["code"], row["module"], row["fingerprint"]) == (code, module, fingerprint):
                row["status"] = "resolved"
                n += 1
        return n

    def for_agents(self) -> list[dict]:
        return [r for r in self.rows if r["status"] == "active" and r["agent_facing"]]
