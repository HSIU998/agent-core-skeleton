import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from collections import Counter

from verification import canary, closure_check, daily_checkup
from verification.sandbox_guard import ProductionTouch, SandboxGuard

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "verification" / "examples"


def entry(**over):
    base = {"id": "X-1", "goal": "a user-visible outcome", "measure": "what we count", "threshold": "the pass line",
            "result": "passed", "evidence": "measured 10 -> 2", "mechanism_ok": True, "goal_measured": True}
    base.update(over)
    return base


class ClosureCheckTest(unittest.TestCase):
    def test_complete_ledger_is_closed(self):
        report = closure_check.check([entry(), entry(id="X-2", result="failed", evidence="1 of 4")])
        self.assertTrue(report.ok)
        self.assertEqual(report.by_result, Counter({"passed": 1, "failed": 1}))

    def test_missing_columns_are_red(self):
        report = closure_check.check([entry(goal="", threshold=None)])
        self.assertEqual(sorted(f.rule for f in report.red), ["R1", "R1"])

    def test_passed_without_evidence_is_red(self):
        report = closure_check.check([entry(evidence="")])
        self.assertEqual([f.rule for f in report.red], ["R3"])

    def test_passed_without_measuring_the_goal_is_red(self):
        report = closure_check.check([entry(goal_measured=False)])
        self.assertEqual([f.rule for f in report.red], ["R4"])

    def test_untouched_needs_no_evidence_and_observing_without_since_is_yellow_only(self):
        report = closure_check.check([entry(result="untouched", evidence=""),
                                      entry(id="X-2", result="observing", goal_measured=False)])
        self.assertTrue(report.ok)
        self.assertEqual([f.rule for f in report.yellow], ["Y1"])

    def test_example_ledger_shows_the_two_classic_mistakes(self):
        entries = json.loads((EXAMPLES / "ledger.json").read_text(encoding="utf-8"))
        report = closure_check.check(entries)
        self.assertEqual({(f.entry_id, f.rule) for f in report.red},
                         {("C-5", "R4"), ("C-6", "R1"), ("C-6", "R4")})
        self.assertIn("release blocked", closure_check.render(report))

    def test_counterexample_mechanism_only_check_passes_an_unfinished_ledger(self):
        # Every change reports "my code ran", so the old check is green - while two of
        # them were never measured against their goal and one has no goal at all.
        entries = [entry(), entry(id="X-2", goal_measured=False), entry(id="X-3", goal="", goal_measured=False)]
        self.assertTrue(closure_check.mechanism_only_check(entries))
        self.assertEqual(len(closure_check.check(entries).red), 3)


SOURCE = """def floor(value, low):
    limit = 3
    done = True
    if value <= low:
        return low
    return value

def grow(v, hours, cap=8):
    hours = min(hours, cap)
    if hours >= 1 and not v is None:
        return v + hours
    return v
"""


def diff_reviewer(clean: str):
    """A reviewer that knows the clean source: flags exactly the changed lines."""
    clean_lines = clean.splitlines()

    def review(code: str) -> set:
        return {i for i, (a, b) in enumerate(zip(clean_lines, code.splitlines()), 1) if a != b}
    return review


def lgtm_reviewer(code: str) -> set:
    return set()


def flag_everything_reviewer(code: str) -> set:
    return set(range(1, len(code.splitlines()) + 1))


class CanaryTest(unittest.TestCase):
    def test_seed_is_deterministic_and_changes_only_the_chosen_lines(self):
        mutated_a, muts_a = canary.seed(SOURCE, 3, rng_seed=7)
        mutated_b, muts_b = canary.seed(SOURCE, 3, rng_seed=7)
        self.assertEqual(mutated_a, mutated_b)
        self.assertEqual(muts_a, muts_b)
        changed = {i for i, (a, b) in enumerate(zip(SOURCE.splitlines(), mutated_a.splitlines()), 1) if a != b}
        self.assertEqual(changed, {m.line for m in muts_a})
        self.assertEqual(len(changed), 3)

    def test_seed_refuses_more_errors_than_mutable_lines(self):
        with self.assertRaises(ValueError):
            canary.seed(SOURCE, 99)

    def test_perfect_reviewer_is_trusted(self):
        result, _ = canary.run(SOURCE, diff_reviewer(SOURCE), n=3)
        self.assertEqual((result.recall, result.false_alarms), (1.0, 0))
        self.assertTrue(result.trusted)

    def test_lgtm_reviewer_is_not_trusted(self):
        result, _ = canary.run(SOURCE, lgtm_reviewer, n=3)
        self.assertEqual(result.recall, 0.0)
        self.assertFalse(result.trusted)

    def test_counterexample_recall_alone_trusts_the_reviewer_that_flags_everything(self):
        _, muts = canary.seed(SOURCE, 3)
        self.assertEqual(canary.recall_only_score(muts, flag_everything_reviewer(SOURCE)), 1.0)
        result, _ = canary.run(SOURCE, flag_everything_reviewer, n=3)
        self.assertEqual(result.recall, 1.0)
        self.assertFalse(result.trusted)  # only the clean-copy measurement exposes it


class SandboxGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prod = pathlib.Path(self.tmp.name) / "production"
        self.sandbox = pathlib.Path(self.tmp.name) / "sandbox"
        self.prod.mkdir()
        self.sandbox.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def guard(self, **kw):
        return SandboxGuard(production_roots=[self.prod], production_endpoints=["127.0.0.1:9000"],
                            production_commands=["live-daemon"], **kw)

    def test_canaries_are_all_caught_before_use(self):
        with self.guard() as g:
            self.assertEqual(g.release_canaries(), {"released": 3, "caught": 3})
            self.assertTrue(g.armed)
            self.assertEqual(g.counts["blocked_writes"], 0)  # canaries do not count as real attempts
        self.assertFalse((self.prod / "__canary__.tmp").exists())

    def test_canaries_need_an_active_guard(self):
        with self.assertRaises(RuntimeError):
            self.guard().release_canaries()

    def test_production_write_is_blocked_and_counted_sandbox_write_is_allowed(self):
        with self.guard() as g:
            with self.assertRaises(ProductionTouch):
                (self.prod / "state.db").write_text("x", encoding="utf-8")
            (self.sandbox / "state.db").write_text("x", encoding="utf-8")
            self.assertEqual((g.counts["blocked_writes"], g.counts["allowed_writes"]), (1, 1))
        self.assertFalse((self.prod / "state.db").exists())
        self.assertTrue((self.sandbox / "state.db").exists())

    def test_reads_from_production_are_fine(self):
        (self.prod / "config.json").write_text("{}", encoding="utf-8")
        with self.guard():
            self.assertEqual((self.prod / "config.json").read_text(encoding="utf-8"), "{}")

    def test_endpoint_and_launch_are_blocked(self):
        with self.guard() as g:
            with self.assertRaises(ProductionTouch):
                g.check_endpoint("127.0.0.1:9000")
            g.check_endpoint("127.0.0.1:9100")  # the sandbox copy
            with self.assertRaises(ProductionTouch):
                g.check_launch(["/opt/bin/live-daemon", "--start"])
            self.assertEqual((g.counts["blocked_endpoints"], g.counts["blocked_launches"]), (1, 1))

    def test_record_mode_counts_without_raising(self):
        with self.guard(mode="record") as g:
            (self.prod / "note.txt").write_text("x", encoding="utf-8")
            self.assertEqual(g.counts["blocked_writes"], 1)
            self.assertFalse(g.armed)
        self.assertTrue((self.prod / "note.txt").exists())  # record mode lets it through, by design

    def test_open_is_restored_after_the_block(self):
        import builtins
        before = builtins.open
        with self.guard():
            self.assertIsNot(builtins.open, before)
        self.assertIs(builtins.open, before)

    def test_counterexample_without_the_guard_the_test_writes_into_production(self):
        def the_test():
            (self.prod / "memories.db").write_text("polluted", encoding="utf-8")
        the_test()
        self.assertTrue((self.prod / "memories.db").exists())  # nothing stopped it, nothing counted it
        os.remove(self.prod / "memories.db")
        with self.guard() as g:
            with self.assertRaises(ProductionTouch):
                the_test()
            self.assertEqual(g.counts["blocked_writes"], 1)
        self.assertFalse((self.prod / "memories.db").exists())


class DailyCheckupTest(unittest.TestCase):
    def setUp(self):
        self.known = json.loads((EXAMPLES / "known.json").read_text(encoding="utf-8"))
        self.baseline = json.loads((EXAMPLES / "baseline.json").read_text(encoding="utf-8"))
        with open(EXAMPLES / "today.log", encoding="utf-8") as fh:
            self.today = daily_checkup.extract(fh)

    def test_signatures_are_rule_and_module(self):
        self.assertEqual(self.today, Counter({"fallback:embedding": 3, "skipped:backup": 1,
                                              "error:router": 1, "timeout:vision": 7}))

    def test_new_and_worse_come_first_known_below_fixed_last(self):
        report = daily_checkup.classify(self.today, self.baseline, self.known)
        self.assertEqual([(i.signature, i.status) for i in report.items],
                         [("error:router", "new"), ("timeout:vision", "worse"),
                          ("fallback:embedding", "known"), ("skipped:backup", "known"),
                          ("^error:watchdog", "fixed")])

    def test_worse_needs_a_baseline(self):
        report = daily_checkup.classify(Counter({"timeout:vision": 7}), {}, self.known)
        self.assertEqual(report.items[0].status, "known")

    def test_render_puts_the_new_one_on_the_first_line(self):
        text = daily_checkup.render(daily_checkup.classify(self.today, self.baseline, self.known))
        self.assertTrue(text.splitlines()[1].startswith("- NEW   error:router"))
        self.assertIn("drop from known", text)

    def test_checkup_is_read_only(self):
        before = {p.name: p.read_bytes() for p in EXAMPLES.iterdir()}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            daily_checkup.main([str(EXAMPLES / "today.log"), "--known", str(EXAMPLES / "known.json"),
                                "--baseline", str(EXAMPLES / "baseline.json")])
        self.assertIn("NEW   error:router", out.getvalue())
        self.assertEqual(before, {p.name: p.read_bytes() for p in EXAMPLES.iterdir()})

    def test_counterexample_naive_report_buries_the_new_problem(self):
        # eleven chronic signatures plus one new one: sorted by count, the new one is last
        today = Counter({f"fallback:service{i}": 20 + i for i in range(11)})
        today["error:router"] = 1
        known = [{"pattern": "^fallback:", "name": "chronic"}]
        self.assertEqual(daily_checkup.naive_report(today)[-1], "error:router")
        report = daily_checkup.classify(today, {}, known)
        self.assertEqual(report.items[0].signature, "error:router")


if __name__ == "__main__":
    unittest.main()
