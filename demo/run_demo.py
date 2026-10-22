import json
import pathlib
import time

from .gate import CoreGuard
from .mouths import TerseMouth, from_env
from .state import FLOOR, DriveState
from .store import MemoryStore
from .turn import run_turn

HERE = pathlib.Path(__file__).parent


def load(name):
    return json.loads((HERE / "personas" / f"{name}.json").read_text(encoding="utf-8"))


def main():
    store = MemoryStore()
    a, b = load("persona_a"), load("persona_b")
    day = 86400
    now = time.time()
    store.add("persona_a", "We planned a trip to the coast for the autumn holiday.", now - 40 * day)
    store.add("persona_a", "The coast trip got moved to the spring.", now - 5 * day)
    store.add("persona_a", "The trip to the coast was moved to spring.", now - 4 * day)
    store.add("persona_b", "The coast is too cold for me.", now - 2 * day)

    print("1) program recalls before the mouth speaks")
    first = run_turn(store, a, "What happened with the coast trip?", from_env())
    print("  ", first["reply"])
    print("   recalled ids:", first["recalled_ids"], "| prefetch ran:", first["prefetch_ran"])

    print("2) swap the mouth (model), ask again")
    second = run_turn(store, a, "What happened with the coast trip?", TerseMouth())
    print("  ", second["reply"])
    same = first["recalled_ids"][:2] == second["recalled_ids"][:2]
    print("   same top memories after swap:", same, "| B's memory leaked into A:",
          any("too cold" in store.db.execute("SELECT text FROM memories WHERE id=?", (i,)).fetchone()[0]
              for i in second["recalled_ids"]))

    print("3) try to rename the persona through the gate")
    guard = CoreGuard()
    print("   rename ->", guard.write(a, "name", "someone else", source="model_output"), "| name is still:", a["name"])
    print("   self description ->", guard.write(a, "self_description", "likes the sea", source="model_output"))
    print("   audit rows:", len(guard.audit))

    print("4) drives over 72 hours with 50 satisfactions")
    d = DriveState()
    lowest = 1.0
    for i in range(72):
        d.grow(1)
        if i < 50:
            d.satisfy("talk")
        lowest = min(lowest, *d.values.values())
    print(f"   lowest value seen: {lowest:.4f} (floor {FLOOR})")


if __name__ == "__main__":
    main()
