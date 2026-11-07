import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))

import build_recording_plan as P  # noqa: E402

OUT = ROOT / "out" / "live"
HAVE = (OUT / "results.json").exists()


@unittest.skipUnless(HAVE, "out/live has not been generated (run: python live_call.py --run)")
class TestRecordingPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
        q = OUT / "results_bike10.json"
        cls.quiet = json.loads(q.read_text(encoding="utf-8")) if q.exists() else None
        cls.rows, cls.total = P.build_timeline(cls.res)

    def test_fits_in_sixty_seconds_with_slack(self):
        self.assertLessEqual(self.total, P.LIMIT - P.MIN_SLACK)

    def test_the_narrator_never_talks_while_the_call_plays(self):
        for a, b in zip(self.rows, self.rows[1:]):
            self.assertLess(a["start"] + a["seconds"], b["start"], (a, b))
        kinds = [r["kind"] for r in self.rows]
        self.assertEqual(kinds.count("call"), 1)
        call = kinds.index("call")
        self.assertEqual(kinds[call - 1], "vo")                                  # something is said before it ...
        self.assertTrue(all(k == "vo" for k in kinds[call + 1:]))                # ... and everything else after it

    def test_the_call_length_comes_from_the_saved_timings(self):
        t = self.res["turns"][0]
        longer = dict(self.res, turns=[dict(t, audio_s=t["audio_s"] + 10)] + self.res["turns"][1:])
        self.assertAlmostEqual(P.call_seconds(longer) - P.call_seconds(self.res), 10, places=6)

    def test_narration_makes_none_of_the_claims_the_project_cannot_support(self):
        narration = " ".join(r["text"] for r in self.rows if r["kind"] == "vo").lower()
        for phrase in P.FORBIDDEN:
            self.assertNotIn(phrase, narration, phrase)

    def test_the_close_says_what_must_be_said(self):
        close = [r["text"] for r in self.rows if r["kind"] == "vo"][-1].lower()
        for needle in ("gnani prisma and timbre", "synthetic", "native review"):
            self.assertIn(needle, close)

    def test_the_run_shows_a_translation_a_partial_translation_and_a_refusal(self):
        statuses = {t["status"] for t in self.res["turns"]}
        self.assertTrue({"translated", "partial", "untranslated"} <= statuses)

    def test_the_plan_file_is_up_to_date_and_complete(self):
        text = P.render(self.res, self.quiet)
        self.assertEqual((ROOT / "RECORDING_PLAN.md").read_text(encoding="utf-8"), text, "stale: run python build_recording_plan.py")
        for needle in ("1920×1080", "#GnaniAI", "#GreatIndianAIInternshipChallenge", "10 November 2026", "tag Gnani AI's official account",
                       "What not to claim", "Do not speak while the call is running", "have not tested it on your machine",
                       "What you will see during the call", "AI fallback"):
            self.assertIn(needle, text, needle)

    def test_every_turn_of_the_run_is_listed_with_what_the_viewer_sees(self):
        text = P.render(self.res, self.quiet)
        for t in self.res["turns"]:
            self.assertIn(f"`{t['heard']}`", text)
            self.assertIn(P.STATUS[t["status"]], text)

    def test_every_do_not_claim_is_something_the_documents_also_disclaim(self):
        sub = (ROOT / "SUBMISSION.md").read_text(encoding="utf-8")
        for needle in ("scripted", "native-speaker review", "No buyer has said they would pay", "synthetic", "not streaming"):
            self.assertIn(needle, sub, needle)


if __name__ == "__main__":
    unittest.main()
