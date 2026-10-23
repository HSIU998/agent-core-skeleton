import unittest

from reliability.alarms import CHRONIC_COUNT, AlarmCenter
from reliability.fail_loud import parse_fields, parse_with_defaults
from reliability.failover import AllBackendsFailed, Backend, FailoverChain


def ok(text):
    return lambda prompt: text


def down(prompt):
    raise ConnectionError("quota exhausted")


class FailoverTests(unittest.TestCase):
    def test_falls_through_to_local_and_counts_it(self):
        chain = FailoverChain([Backend("cloud-a", "vendor-a", down),
                               Backend("cloud-b", "vendor-b", down),
                               Backend("local", "this-machine", ok("hi"))])
        self.assertEqual(chain.complete("x"), ("hi", "local"))
        self.assertEqual(chain.failures, {"cloud-a": 1, "cloud-b": 1})
        self.assertEqual(chain.used, {"local": 1})

    def test_reports_every_reason_when_all_fail(self):
        chain = FailoverChain([Backend("a", "v1", down), Backend("b", "v2", down)])
        with self.assertRaises(AllBackendsFailed) as cm:
            chain.complete("x")
        self.assertIn("a: ConnectionError", str(cm.exception))
        self.assertIn("b: ConnectionError", str(cm.exception))

    def test_counterexample_backup_equal_to_primary_is_flagged(self):
        chain = FailoverChain([Backend("model-pro", "vendor-a", down), Backend("model-pro", "vendor-a", down)])
        problems = chain.problems()
        self.assertEqual(len(problems), 2)
        with self.assertRaises(AllBackendsFailed):
            chain.complete("x")  # one outage, nothing answers

    def test_healthy_chain_has_no_problems(self):
        chain = FailoverChain([Backend("a", "v1", ok("")), Backend("local", "machine", ok(""))])
        self.assertEqual(chain.problems(), [])


class FailLoudTests(unittest.TestCase):
    REQUIRED = {"mood": str, "brightness": float}

    def test_good_output_parses(self):
        p = parse_fields('Sure: {"mood": "calm", "brightness": 0.8}', self.REQUIRED)
        self.assertTrue(p.ok)
        self.assertEqual(p.data["brightness"], 0.8)

    def test_garbage_is_a_failure_not_a_value(self):
        p = parse_fields("I could not see the image clearly.", self.REQUIRED)
        self.assertFalse(p.ok)
        self.assertEqual(p.data, {})

    def test_counterexample_defaults_make_garbage_look_normal(self):
        defaults = {"mood": "neutral", "brightness": 0.5}
        silent = parse_with_defaults("I could not see the image clearly.", defaults)
        real = parse_with_defaults('{"mood": "neutral", "brightness": 0.5}', defaults)
        self.assertEqual(silent, real)  # downstream cannot tell failure from a real answer


class AlarmTests(unittest.TestCase):
    def test_repeats_collapse_into_one_chronic_row(self):
        center = AlarmCenter()
        for _ in range(CHRONIC_COUNT):
            center.trigger("E-DISK", "backup", "target not mounted")
        self.assertEqual(len(center.rows), 1)
        self.assertTrue(center.rows[0]["chronic"])

    def test_machine_faults_do_not_reach_agents_by_default(self):
        center = AlarmCenter()
        center.trigger("E-MON", "monitor", "monitor disconnected")
        center.trigger("E-NOTE", "notes", "your note was saved late", agent_facing=True)
        self.assertEqual([r["code"] for r in center.for_agents()], ["E-NOTE"])

    def test_resolved_alarm_starts_a_new_row_when_it_returns(self):
        center = AlarmCenter()
        center.trigger("E-DISK", "backup", "x")
        center.resolve("E-DISK", "backup")
        center.trigger("E-DISK", "backup", "x")
        self.assertEqual([r["status"] for r in center.rows], ["resolved", "active"])


if __name__ == "__main__":
    unittest.main()
