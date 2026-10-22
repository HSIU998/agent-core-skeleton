import time
import unittest

from demo.gate import CoreGuard
from demo.mouths import EchoMouth, TerseMouth
from demo.state import FLOOR, DriveState
from demo.store import MemoryStore
from demo.turn import run_turn

A = {"persona_id": "persona_a", "name": "A", "self_description": ""}


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        now = time.time()
        self.old = self.store.add("persona_a", "We planned a trip to the coast.", now - 40 * 86400)
        self.new = self.store.add("persona_a", "The coast trip moved to spring.", now - 86400)
        self.store.add("persona_b", "The coast is too cold.", now)

    def test_prefetch_runs_every_turn(self):
        for _ in range(16):
            self.assertTrue(run_turn(self.store, A, "coast trip?", EchoMouth())["prefetch_ran"])

    def test_swap_mouth_keeps_memory(self):
        before = run_turn(self.store, A, "coast trip?", EchoMouth())["recalled_ids"][:2]
        after = run_turn(self.store, A, "coast trip?", TerseMouth())["recalled_ids"][:2]
        self.assertEqual(before, after)
        self.assertIn(self.new, after)

    def test_dialogue_does_not_enter_recall_pool(self):
        before = self.store.count("persona_a")
        run_turn(self.store, A, "coast trip?", EchoMouth())
        self.assertEqual(self.store.count("persona_a"), before)

    def test_personas_do_not_share_memory(self):
        texts = [m["text"] for m in self.store.recall("persona_a", "coast", limit=10)]
        self.assertFalse(any("too cold" in t for t in texts))

    def test_recent_ranks_above_old_when_equally_relevant(self):
        ids = [m["id"] for m in self.store.recall("persona_a", "coast trip", limit=2)]
        self.assertEqual(ids[0], self.new)

    def test_gate_denies_rename_and_logs_it(self):
        core = dict(A)
        g = CoreGuard()
        self.assertEqual(g.write(core, "name", "X", "model_output"), "deny")
        self.assertEqual(core["name"], "A")
        self.assertEqual(g.audit[-1]["verdict"], "deny")

    def test_drive_never_reaches_zero(self):
        d = DriveState()
        for _ in range(500):
            d.satisfy("talk")
            d.grow(0)
        self.assertGreaterEqual(min(d.values.values()), FLOOR)
        self.assertGreater(d.values["talk"], 0)


if __name__ == "__main__":
    unittest.main()
