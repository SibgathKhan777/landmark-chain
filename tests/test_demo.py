import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import demo  # noqa: E402
import gnani  # noqa: E402


class FakeApi:
    """Offline stand-in: 'speech' is a short silent clip and Prisma returns what was spoken.

    mode "readback": on the first try the temple phrase loses its relation word ("देवळाच्या आहे"),
                     which should trigger a yes/no read-back
    mode "empty":    on the first try at 0 dB Prisma returns nothing
    mode "clean":    Prisma returns exactly what was said
    mode "stress":   clean everywhere except babble, where the temple phrase loses its relation word
    mode "stress_dead": clean everywhere except babble, where Prisma returns nothing
    """

    def __init__(self, mode="readback"):
        self.calls = {"tts": 0, "stt": 0}
        self.mode = mode

    def tts(self, text, voice, lang, hint=None):
        self.calls["tts"] += 1
        return gnani.write_wav([200] * 8000, 16000)

    def stt(self, audio, lang, hint=None, ctx=None):
        self.calls["stt"] += 1
        ctx = ctx or {}
        if ctx.get("kind") == "babble" and not ctx.get("ladder") and ctx.get("state") != "AWAIT_YN":
            if self.mode == "stress" and ctx.get("attempt") == 1 and "देवळाच्या" in hint:
                return hint.replace(" मागे", "")
            if self.mode == "stress_dead":
                return ""
        if ctx.get("state") == "AWAIT_YN" or ctx.get("ladder") or ctx.get("attempt") != 1:
            return hint
        if self.mode == "readback" and "देवळाच्या" in hint:
            return hint.replace(" मागे", "")                  # relation word lost
        if self.mode == "empty" and ctx.get("snr") == 0:
            return ""
        return hint


class TestDemo(unittest.TestCase):
    def run_demo(self, mode="readback", stress=False):
        d = tempfile.mkdtemp()
        res = demo.run(FakeApi(mode), d, "mr-IN", clock=lambda: 1_800_000_000.0, stress=stress)
        return res, Path(d)

    def test_customers_in_two_languages_merge_into_one_route(self):
        res, _ = self.run_demo()
        self.assertEqual(len(res["customers"]), 4)
        self.assertEqual(len(res["route_before"]), 3)                    # temple, blue gate, green house
        blue = [r for r in res["route_before"] if "नीला" in r["text"] or "निळे" in r["text"]][0]
        self.assertEqual(blue["support"], 3.0)                            # 3 of 4 customers; the red gate lost
        self.assertEqual(blue["alternatives"], 1)

    def test_rider_hears_the_route_in_marathi(self):
        res, _ = self.run_demo()
        self.assertEqual(res["steps"][0]["phrase"], "देवळाच्या मागे")
        self.assertTrue(all(s["rendered"] for s in res["steps"]))

    def test_missing_relation_triggers_a_read_back_then_confirms(self):
        res, _ = self.run_demo("readback")
        s = res["steps"][0]
        self.assertEqual([a["action"] for a in s["attempts"]], ["CONFIRM_YN", "CONFIRMED"])
        self.assertEqual((s["status"], s["method"]), ("CONFIRMED", "yes"))

    def test_empty_transcript_asks_again_then_confirms_by_voice(self):
        res, _ = self.run_demo("empty")
        s = [x for x in res["steps"] if x["snr"] == 0][0]
        self.assertEqual([a["action"] for a in s["attempts"]], ["ASK_AGAIN", "CONFIRMED"])
        self.assertEqual(s["method"], "voice")

    def test_clear_audio_is_accepted_by_voice(self):
        res, _ = self.run_demo("clean")
        self.assertTrue(all(s["status"] == "CONFIRMED" and s["method"] == "voice" for s in res["steps"]))

    def test_confidence_rises_after_rider_confirmations(self):
        res, _ = self.run_demo("clean")
        before = {r["text"]: r["confidence"] for r in res["route_before"]}
        after = {r["text"]: r["confidence"] for r in res["route_after"]}
        self.assertTrue(all(after[k] > before[k] for k in before))

    def test_noise_ladder_has_four_conditions(self):
        res, _ = self.run_demo()
        self.assertEqual([r["cond"] for r in res["ladder"]], ["bike@10", "bike@5", "bike@0", "babble@5"])

    def test_outputs_are_written(self):
        res, d = self.run_demo()
        for name in ("demo_log.md", "storyboard.md", "demo_sequence.wav", "results.json", "demo.db"):
            self.assertTrue((d / name).exists(), name)
        with wave.open(str(d / "demo_sequence.wav")) as w:
            self.assertGreater(w.getnframes() / w.getframerate(), 5)
        story = (d / "storyboard.md").read_text(encoding="utf-8")
        self.assertIn("Synthetic voices", story)
        self.assertIn("#GnaniAI", story)
        self.assertIn("#GreatIndianAIInternshipChallenge", story)

    def test_no_route_is_reported_not_crashed(self):
        class Silent(FakeApi):
            def stt(self, *a, **k):
                return ""
        d = tempfile.mkdtemp()
        res = demo.run(Silent(), d, "mr-IN", clock=lambda: 1_800_000_000.0)
        self.assertIn("error", res)



class TestStressScene(unittest.TestCase):
    def run_demo(self, mode, stress=True):
        d = tempfile.mkdtemp()
        res = demo.run(FakeApi(mode), d, "mr-IN", clock=lambda: 1_800_000_000.0, stress=stress)
        return res, Path(d)

    def test_off_by_default(self):
        res, d = self.run_demo("stress", stress=False)
        self.assertNotIn("stress", res)
        self.assertEqual(list(d.glob("4_stress*")), [])

    def test_uses_the_landmark_with_most_critical_words_and_babble_at_5db(self):
        res, _ = self.run_demo("stress")
        st = res["stress"]
        self.assertEqual(st["phrase"], "देवळाच्या मागे")        # anchor + relation: a read-back is possible
        self.assertEqual((st["kind"], st["snr"]), ("babble", 5))

    def test_shows_the_read_back_path(self):
        res, _ = self.run_demo("stress")
        st = res["stress"]
        self.assertEqual([a["action"] for a in st["attempts"]], ["CONFIRM_YN", "CONFIRMED"])
        self.assertEqual((st["status"], st["method"]), ("CONFIRMED", "yes"))

    def test_tap_fallback_is_reported_not_faked(self):
        res, _ = self.run_demo("stress_dead")
        st = res["stress"]
        self.assertEqual([a["action"] for a in st["attempts"]], ["ASK_AGAIN", "ASK_AGAIN", "FALLBACK_TAP"])
        self.assertEqual(st["status"], "AWAITING_TAP")
        self.assertIsNone(st["method"])

    def test_stress_does_not_touch_the_store(self):
        with_stress, _ = self.run_demo("stress", stress=True)
        without, _ = self.run_demo("stress", stress=False)
        self.assertEqual(with_stress["route_after"], without["route_after"])
        self.assertEqual(with_stress["steps"], without["steps"])

    def test_seeds_are_fixed_and_differ_per_attempt(self):
        a, _ = self.run_demo("stress")
        b, _ = self.run_demo("stress")
        self.assertEqual(a["stress"]["seeds"], b["stress"]["seeds"])
        self.assertEqual(len(set(a["stress"]["seeds"])), len(a["stress"]["seeds"]))

    def test_log_and_storyboard_mention_the_stress_result(self):
        _, d = self.run_demo("stress")
        log = (d / "demo_log.md").read_text(encoding="utf-8")
        self.assertIn("Scene 4: stress", log)
        self.assertIn("not added to the store", log.lower())
        self.assertIn("Stress scene", (d / "storyboard.md").read_text(encoding="utf-8"))


class TestReplayScene(unittest.TestCase):
    HEADER = ["part", "lang", "group", "idx", "cond", "ref", "hyp"]
    ROWS = [
        ["hard", "mr-IN", "M-A", "0", "clean", "देवळाच्या मागे निळे गेट", "देवळाच्या मागे निळे गेट"],       # accept
        ["hard", "mr-IN", "M-A", "0", "babble@5", "देवळाच्या मागे निळे गेट", "देवळाच्या मागे"],           # first read-back
        ["hard", "hi-IN", "H-B", "2", "babble@5", "दूसरी गली में पीला मकान", ""],                         # first ask-again
        ["hard", "mr-IN", "M-C", "1", "bike@0", "डाव्या बाजूला पहिले दुकान", "डाव्या बाजूला"],             # later read-back
        ["orig", "hi-IN", "orig", "0", "bike@0", "मंदिर के पीछे नीला गेट", "मंदिर के पीछे"],               # not the 24-phrase set
        ["hard", "hi-IN", "H-A", "0", "bike@5", "मंदिर के पीछे नीला गेट", "मंदिर के पीछे लाल गेट"],        # mismatch
    ]

    def make_csv(self, rows=None):
        import csv
        path = Path(tempfile.mkdtemp()) / "hard_results.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(self.HEADER)
            w.writerows(self.ROWS if rows is None else rows)
        return path

    def run_demo(self, replay=True, csv_path=None):
        d = tempfile.mkdtemp()
        api = FakeApi("clean")
        res = demo.run(api, d, "mr-IN", clock=lambda: 1_800_000_000.0, replay=replay,
                       sweep_csv=csv_path or self.make_csv())
        return res, Path(d), api

    def test_off_by_default(self):
        res, d, _ = self.run_demo(replay=False)
        self.assertNotIn("replay", res)
        self.assertEqual(list(d.glob("5_replay*")), [])
        self.assertFalse((d / "replay_sequence.wav").exists())

    def test_picks_the_first_read_back_and_first_ask_again_in_file_order(self):
        res, _, _ = self.run_demo()
        cases = res["replay"]["cases"]
        self.assertEqual([c["expected"] for c in cases], ["देवळाच्या मागे निळे गेट", "दूसरी गली में पीला मकान"])
        self.assertEqual([c["sweep_csv_line"] for c in cases], [3, 4])        # header is line 1

    def test_counts_cover_every_sweep_row_of_the_24_phrase_set(self):
        res, _, _ = self.run_demo()
        rp = res["replay"]
        self.assertEqual(rp["total"], 5)                                      # the 'orig' row is excluded
        self.assertEqual(rp["counts"], {"ACCEPT": 1, "CONFIRM": 2, "ASK_AGAIN": 1, "MISMATCH": 1})

    def test_read_back_case_uses_a_recorded_transcript_and_a_labelled_scripted_reply(self):
        res, _, _ = self.run_demo()
        c = res["replay"]["cases"][0]
        self.assertEqual([s["action"] for s in c["steps"]], ["CONFIRM_YN", "CONFIRMED"])
        self.assertEqual([s["source"] for s in c["steps"]], ["recorded Prisma transcript", "scripted reply, not recorded"])
        self.assertEqual(c["steps"][0]["text"], "देवळाच्या मागे")
        self.assertEqual(c["status"], "CONFIRMED")
        self.assertIn("बरोबर", c["steps"][0]["bot_says"])                    # Marathi prompt for a Marathi case

    def test_ask_again_case_stops_without_inventing_a_second_attempt(self):
        res, _, _ = self.run_demo()
        c = res["replay"]["cases"][1]
        self.assertEqual([s["action"] for s in c["steps"]], ["ASK_AGAIN"])
        self.assertEqual(c["status"], "UNRESOLVED")
        self.assertIn("no real second attempt", c["note"])
        self.assertIn("दोबारा", c["steps"][0]["bot_says"])                   # Hindi prompt for a Hindi case

    def test_prisma_is_not_called_and_this_runs_results_are_untouched(self):
        with_replay, d1, api1 = self.run_demo(replay=True)
        without, d2, api2 = self.run_demo(replay=False)
        self.assertEqual(api1.calls["stt"], api2.calls["stt"])
        self.assertGreater(api1.calls["tts"], api2.calls["tts"])              # only bot prompts were added
        for key in ("route_after", "steps", "ladder", "customers"):
            self.assertEqual(with_replay[key], without[key])

    def test_replay_audio_is_kept_out_of_this_runs_sequence(self):
        _, d1, _ = self.run_demo(replay=True)
        _, d2, _ = self.run_demo(replay=False)
        self.assertGreaterEqual(len(list(d1.glob("5_replay_case*_bot_*.wav"))), 3)
        self.assertTrue((d1 / "replay_sequence.wav").exists())
        with wave.open(str(d1 / "demo_sequence.wav")) as a, wave.open(str(d2 / "demo_sequence.wav")) as b:
            self.assertEqual(a.getnframes(), b.getnframes())

    def test_everything_is_labelled(self):
        _, d, _ = self.run_demo()
        log = (d / "demo_log.md").read_text(encoding="utf-8")
        self.assertIn("REPLAYED FROM THE SWEEP, NOT FROM THIS RUN", log)
        self.assertIn("recorded Prisma transcript", log)
        self.assertIn("scripted reply, not recorded", log)
        self.assertIn("Prisma was not called", log)
        story = (d / "storyboard.md").read_text(encoding="utf-8")
        self.assertIn("Replayed from an earlier test run", story)

    def test_missing_sweep_file_is_reported_not_crashed(self):
        res, d, _ = self.run_demo(csv_path=Path(tempfile.mkdtemp()) / "nope.csv")
        self.assertIn("not found", res["replay"]["error"])
        self.assertIn("Not run", (d / "demo_log.md").read_text(encoding="utf-8"))

    def test_sweep_with_nothing_to_replay_yields_no_cases(self):
        res, _, _ = self.run_demo(csv_path=self.make_csv(self.ROWS[:1]))
        self.assertEqual(res["replay"]["cases"], [])


class TestNetworkCheck(unittest.TestCase):
    def test_reports_failure_instead_of_raising(self):
        import socket
        real = socket.create_connection
        socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("name resolution failed"))
        try:
            ok, msg = gnani.check_network(timeout=1)
        finally:
            socket.create_connection = real
        self.assertFalse(ok)
        self.assertIn("name resolution", msg)

    def test_a_hanging_lookup_times_out(self):
        import socket
        import time
        real = socket.create_connection
        def hang(*a, **k):
            time.sleep(3)
            raise OSError("late")          # the abandoned probe thread ends cleanly
        socket.create_connection = hang
        try:
            t0 = time.monotonic()
            ok, _ = gnani.check_network(timeout=1)
            elapsed = time.monotonic() - t0
        finally:
            socket.create_connection = real
        self.assertFalse(ok)
        self.assertLess(elapsed, 4)


if __name__ == "__main__":
    unittest.main()
