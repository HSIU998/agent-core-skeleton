import time
import unittest

from retrieval.hybrid import mmr, rank
from retrieval.index import KeywordIndex
from retrieval.keywords import extract_keywords, segment
from retrieval.router import route

DAY = 86400


class KeywordTests(unittest.TestCase):
    def test_keeps_rare_words_and_drops_common_ones(self):
        df = {"coast": 2, "trip": 40, "holiday": 1}.get
        keys = extract_keywords("the coast trip holiday", lambda w: df(w, 0), total=100, use_jieba=False)
        self.assertEqual(keys, ["holiday", "coast"])  # rarest first; "trip" is in 40% of memories

    def test_words_missing_from_memory_are_not_keys(self):
        keys = extract_keywords("hokkaido trip", lambda w: 0, total=100, use_jieba=False)
        self.assertEqual(keys, [])

    @unittest.skipUnless(__import__("importlib").util.find_spec("jieba") and __import__("importlib").util.find_spec("opencc"),
                         "jieba and opencc not installed")
    def test_traditional_text_keeps_its_own_characters(self):
        toks = segment("我們上次去海邊旅行", use_jieba=True)
        self.assertTrue(all("边" not in t for t in toks))  # segmented in Simplified, returned in Traditional
        self.assertIn("海邊", "".join(toks))


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.idx = KeywordIndex(use_jieba=False)
        self.idx.add("persona_a", 1, "we talked about the weather and the weather again")
        self.idx.add("persona_a", 2, "the lighthouse trip got moved to spring")
        self.idx.add("persona_a", 3, "weather was fine")
        self.idx.add("persona_a", 5, "the weather report for today")
        self.idx.add("persona_b", 4, "the pier is too cold for me")

    def test_bm25_puts_the_rare_word_first(self):
        hits = self.idx.search("persona_a", "lighthouse weather")
        self.assertEqual(hits[0][0], 2)

    def test_counterexample_raw_hit_count_prefers_the_common_word(self):
        # The full-scan approach scores by how many query words appear; the
        # weather chatter wins on raw counts even though "lighthouse" is the point.
        docs = {1: "we talked about the weather and the weather again", 2: "the lighthouse trip got moved to spring"}
        raw = {mid: sum(text.count(w) for w in ("lighthouse", "weather")) for mid, text in docs.items()}
        self.assertEqual(max(raw, key=raw.get), 1)

    def test_personas_do_not_share_the_index(self):
        self.assertNotIn(4, [mid for mid, _ in self.idx.search("persona_a", "pier cold")])
        self.assertIn(4, [mid for mid, _ in self.idx.search("persona_b", "pier cold")])


class HybridTests(unittest.TestCase):
    def setUp(self):
        now = time.time()
        self.now = now
        self.mems = [
            {"id": 1, "text": "the coast trip moved to spring", "ts": now - DAY},
            {"id": 2, "text": "the coast trip was moved to spring", "ts": now - DAY},
            {"id": 3, "text": "we booked a coast hotel near the trip route", "ts": now - 3 * DAY},
        ]

    def test_mmr_keeps_a_different_memory_in_the_top_two(self):
        top = rank("coast trip", self.mems, {}, self.now, limit=2)
        self.assertIn(3, [m["id"] for m in top])

    def test_counterexample_without_mmr_top_two_are_the_same_event(self):
        top = rank("coast trip", self.mems, {}, self.now, limit=2, mmr_lambda=1.0)
        self.assertEqual(sorted(m["id"] for m in top), [1, 2])

    def test_keyword_score_can_lift_a_memory(self):
        base = [m["id"] for m in rank("coast", self.mems, {}, self.now, limit=1)]
        lifted = [m["id"] for m in rank("coast", self.mems, {3: 5.0}, self.now, limit=1)]
        self.assertNotEqual(base, [3])
        self.assertEqual(lifted, [3])


class RouterTests(unittest.TestCase):
    def test_model_answer_is_used_when_valid(self):
        r = route("hi", classify=lambda t: '{"use_memory": true, "use_web": false}')
        self.assertEqual((r["use_memory"], r["source"]), (True, "model"))

    def test_model_failure_falls_back_to_rules(self):
        def broken(_):
            raise TimeoutError("model down")
        r = route("你記得上次去海邊嗎", classify=broken)
        self.assertTrue(r["use_memory"])
        self.assertEqual(r["source"], "rules_after_TimeoutError")

    def test_counterexample_all_false_on_failure_skips_memory(self):
        legacy = {"use_memory": False, "use_web": False}  # what "fail to nothing" returns
        self.assertNotEqual(legacy["use_memory"], route("你記得上次去海邊嗎", classify=lambda t: "not json")["use_memory"])


if __name__ == "__main__":
    unittest.main()
