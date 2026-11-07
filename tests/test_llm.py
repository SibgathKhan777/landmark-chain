import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import llm_fallback  # noqa: E402
from llm_fallback import LlmFallback  # noqa: E402
from test_live import WAV, FakeLive, connected, drain  # noqa: E402


def reply(text):
    return lambda url, headers, body, timeout: {"choices": [{"message": {"content": text}}]}


class TestClient(unittest.TestCase):
    def test_it_is_off_without_an_address(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(llm_fallback, "_dotenv", return_value=""):
            self.assertIsNone(LlmFallback.from_env())
        with mock.patch.dict(os.environ, {"LLM_BASE_URL": "https://x.example/v1", "LLM_API_KEY": "k"}, clear=True):
            c = LlmFallback.from_env()
            self.assertEqual((c.url, c.api_key, c.host), ("https://x.example/v1/chat/completions", "k", "x.example"))

    def test_the_address_may_or_may_not_end_in_v1(self):
        for base in ("https://h.example", "https://h.example/", "https://h.example/v1", "https://h.example/v1/"):
            self.assertEqual(LlmFallback(base).url, "https://h.example/v1/chat/completions", base)

    def test_the_request_has_the_key_the_rules_and_the_examples(self):
        seen = {}

        def post(url, headers, body, timeout):
            seen.update(url=url, headers=headers, body=json.loads(body), timeout=timeout)
            return {"choices": [{"message": {"content": "ಬಲಕ್ಕೆ ತಿರುಗಿ."}}]}
        LlmFallback("https://h.example", "secret", post=post).translate("right le lo", "kn-IN")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer secret")
        msgs = seen["body"]["messages"]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("Kannada script", msgs[0]["content"])
        self.assertEqual(msgs[-1], {"role": "user", "content": "right le lo"})
        self.assertEqual(len(msgs), 1 + 2 * len(llm_fallback.EXAMPLES) + 1)
        self.assertEqual(seen["body"]["temperature"], 0)
        shot_answers = [m["content"] for m in msgs[2:-1:2]]
        self.assertEqual(shot_answers, [e[2] for e in llm_fallback.EXAMPLES])                # the Kannada column for Kannada

    def test_english_uses_the_english_examples_and_no_key_means_no_header(self):
        seen = {}

        def post(url, headers, body, timeout):
            seen.update(headers=headers, body=json.loads(body))
            return {"choices": [{"message": {"content": "Turn right."}}]}
        LlmFallback("https://h.example", post=post).translate("right le lo", "en")
        self.assertNotIn("Authorization", seen["headers"])
        self.assertEqual([m["content"] for m in seen["body"]["messages"][2:-1:2]], [e[1] for e in llm_fallback.EXAMPLES])

    def test_a_matching_answer_is_ok_and_a_mismatching_one_is_rejected_with_the_reason(self):
        good = LlmFallback("https://h.example", post=reply("Turn right after two lanes.")).translate("दो गली बाद राइट ले लो", "en")
        self.assertEqual((good["status"], good["problems"]), ("ok", []))
        bad = LlmFallback("https://h.example", post=reply("Turn right after that lane.")).translate("दो गली बाद राइट ले लो", "en")
        self.assertEqual(bad["status"], "rejected")
        self.assertIn("number", " ".join(bad["problems"]))
        self.assertEqual(bad["output"], "Turn right after that lane.")                    # kept for the log, never spoken

    def test_with_the_check_off_a_rejected_answer_is_still_given_but_marked_unchecked(self):
        bad = LlmFallback("https://h.example", post=reply("Turn right after that lane."), guard_on=False).translate("दो गली बाद राइट ले लो", "en")
        self.assertEqual((bad["status"], bad["checked"]), ("ok", False))
        self.assertIn("number", " ".join(bad["problems"]))                                # what the check WOULD have said is still recorded
        self.assertEqual(LlmFallback("https://h.example", post=reply(""), guard_on=False).translate("seedha aao", "en")["status"], "rejected")
        on = LlmFallback("https://h.example", post=reply("Turn right after that lane.")).translate("दो गली बाद राइट ले लो", "en")
        self.assertEqual((on["status"], on["checked"]), ("rejected", True))               # on by default

    def test_the_switch_is_read_from_the_environment(self):
        with mock.patch.dict(os.environ, {"LLM_BASE_URL": "https://x.example", "LLM_GUARD": "off"}, clear=True):
            self.assertFalse(LlmFallback.from_env().guard_on)
        with mock.patch.dict(os.environ, {"LLM_BASE_URL": "https://x.example"}, clear=True), mock.patch.object(llm_fallback, "_dotenv", return_value=""):
            self.assertTrue(LlmFallback.from_env().guard_on)

    def test_every_failure_is_an_error_not_an_exception(self):
        def boom(*a):
            raise TimeoutError("slow")
        for post in (boom, lambda *a: {"nope": 1}, lambda *a: {"choices": []}):
            r = LlmFallback("https://h.example", post=post).translate("seedha aao", "en")
            self.assertEqual(r["status"], "error", post)
        self.assertEqual(LlmFallback("https://h.example", post=reply("")).translate("seedha aao", "en")["status"], "rejected")
        self.assertEqual(LlmFallback("https://h.example", post=reply("x")).translate("seedha aao", "hi-IN")["status"], "error")

    def test_a_thinking_block_is_dropped(self):
        r = LlmFallback("https://h.example", post=reply("<think>hmm right left</think>Come straight.")).translate("seedha aao", "en")
        self.assertEqual((r["status"], r["output"]), ("ok", "Come straight."))

    def test_an_invented_next_message_is_cut_off(self):
        out = LlmFallback("https://h.example", post=reply("भाई, मैं मुख्य सड़क पर हूँ।\n\n<<user>>\nನೀವು ಎಲ್ಲಿಗೆ ಹೋಗಬೇಕು\n\nYou are going to where?")).translate("ಅಣ್ಣ ನಾನು ಮುಖ್ಯ ರಸ್ತೆಯಲ್ಲಿ", "hi-IN", "kn-IN")
        self.assertEqual(out["output"], "भाई, मैं मुख्य सड़क पर हूँ।")
        self.assertEqual(LlmFallback("https://h.example", post=reply("Come straight. <|im_end|> more")).translate("seedha aao", "en")["output"], "Come straight.")

    def test_the_gloss_is_empty_when_it_fails(self):
        def boom(*a):
            raise OSError("down")
        self.assertEqual(LlmFallback("https://h.example", post=boom).meaning("seedha aao"), "")


class FakeLlm:
    name = "Evon"
    host = "fake"

    def __init__(self, result, gloss="a gloss"):
        self.result, self.gloss, self.asked = result, gloss, []

    def translate(self, text, dst, src="hi-IN"):
        self.asked.append((text, dst) if src == "hi-IN" else (text, dst, src))
        return dict(self.result)

    def meaning(self, text, src="hi-IN"):
        return self.gloss


OK_KN = {"status": "ok", "output": "ಅಣ್ಣಾ ಚಹಾ ಕುಡಿದು ಬನ್ನಿ.", "problems": [], "seconds": 0.7}


def room_with(llm, transcripts):
    r = connected(transcripts)
    r.llm = llm
    return r


class TestRelayWithTheFallback(unittest.TestCase):
    def test_a_refused_sentence_is_translated_by_the_ai_and_labelled(self):
        llm = FakeLlm(OK_KN)
        room = room_with(llm, ["भैया चाय पीकर आना"])
        cust, bike, stage = (room.subscribe(r) for r in ("customer", "biker", "stage"))
        for q in (cust, bike, stage):
            drain(q)
        rec = room.process("customer", WAV)
        self.assertEqual((rec["status"], rec["rules_status"], rec["output"]), ("ai", "untranslated", OK_KN["output"]))
        self.assertEqual(llm.asked, [("भैया चाय पीकर आना", "kn-IN")])
        self.assertEqual(room.api.said[0][0], OK_KN["output"])                              # the AI text is what Timbre speaks
        self.assertEqual(rec["notices"], [])                                                # the speaker is not told it was refused
        c, b, s = drain(cust), drain(bike), drain(stage)
        self.assertEqual(b[0]["status"], "ai")
        self.assertEqual(b[0]["text"], OK_KN["output"])
        self.assertEqual(c[0]["status"], "ai")
        self.assertIn("AI gloss", s[0]["english"])
        self.assertEqual(s[0]["ai"]["name"], "Evon")
        self.assertIn("llm", rec["ms"])

    def test_an_unchecked_answer_is_spoken_and_labelled_as_such(self):
        llm = FakeLlm({"status": "ok", "output": "ಅಣ್ಣಾ ಆರ್ಡರ್ ಬನ್ನಿ.", "problems": ["number: ['2'] said but not in the output"], "seconds": 0.5, "checked": False})
        room = room_with(llm, ["भाई ऑर्डर लाके दे दो यार"])
        bike = room.subscribe("biker"); drain(bike)
        rec = room.process("customer", WAV)
        self.assertEqual((rec["status"], rec["output"]), ("ai_unchecked", "ಅಣ್ಣಾ ಆರ್ಡರ್ ಬನ್ನಿ."))
        self.assertEqual(drain(bike)[0]["status"], "ai_unchecked")

    def test_a_rejected_ai_answer_falls_back_to_the_rules_refusal(self):
        llm = FakeLlm({"status": "rejected", "output": "ಎಡಕ್ಕೆ ತಿರುಗಿ", "problems": ["side: said ['right'], output ['left']"], "seconds": 0.6})
        room = room_with(llm, ["भैया चाय पीकर आना"])
        bike = room.subscribe("biker"); drain(bike)
        rec = room.process("customer", WAV)
        self.assertEqual((rec["status"], rec["ai"]["status"]), ("untranslated", "rejected"))
        self.assertEqual(len(rec["notices"]), 1)                                            # both people are told, as without the AI
        self.assertNotIn("ಎಡಕ್ಕೆ", json.dumps([e for e in drain(bike)], ensure_ascii=False))   # the rejected text never reaches the biker
        self.assertNotIn("ಎಡಕ್ಕೆ", " ".join(t for t, _, _ in room.api.said))

    def test_an_ai_error_changes_nothing(self):
        room = room_with(FakeLlm({"status": "error", "output": "", "problems": [], "seconds": 1, "error": "timeout"}), ["भैया चाय पीकर आना"])
        self.assertEqual(room.process("customer", WAV)["status"], "untranslated")

    def test_the_ai_is_never_asked_when_the_rules_translated_everything(self):
        llm = FakeLlm(OK_KN)
        room = room_with(llm, ["भैया सीधे आ जाओ राइट ले लो"])
        self.assertEqual(room.process("customer", WAV)["status"], "translated")
        self.assertEqual(llm.asked, [])

    def test_a_partial_translation_is_upgraded_only_if_the_ai_passes(self):
        llm = FakeLlm(OK_KN)
        room = room_with(llm, ["भैया मैं पांच मिनट में आ रहा हूँ"])
        rec = room.process("customer", WAV)
        self.assertEqual((rec["rules_status"], rec["status"]), ("partial", "ai"))
        self.assertEqual(len(rec["speaks"]), 1)                                             # one clip: no "rest was not translated" notice

    def test_a_kannada_reply_is_translated_by_the_ai_for_the_customer(self):
        llm = FakeLlm({"status": "ok", "output": "भाई तुम कहाँ हो, मैं यहीं हूँ।", "problems": [], "seconds": 0.8})
        room = room_with(llm, ["ಎಲ್ಲಿದ್ದೀಯ ಬ್ರೋ ನಾನು ಇಲ್ಲೇ ಇದ್ದೀನಿ"])
        cust = room.subscribe("customer"); drain(cust)
        rec = room.process("biker", WAV)
        self.assertEqual((rec["status"], rec["rules_status"], rec["dst"]), ("ai", "untranslated", "hi-IN"))
        self.assertEqual(llm.asked, [("ಎಲ್ಲಿದ್ದೀಯ ಬ್ರೋ ನಾನು ಇಲ್ಲೇ ಇದ್ದೀನಿ", "hi-IN", "kn-IN")])
        e = drain(cust)[0]
        self.assertEqual((e["status"], e["lang"], e["text"]), ("ai", "hi-IN", "भाई तुम कहाँ हो, मैं यहीं हूँ।"))
        self.assertEqual(room.api.said[0][1:], ("Nalini", "hi-IN"))

    def test_the_ai_is_not_asked_when_there_is_nothing_to_translate(self):
        llm = FakeLlm(OK_KN)
        room2 = room_with(llm, [""])
        room2.process("customer", WAV)                                                     # silence
        self.assertEqual(llm.asked, [])

    def test_english_listeners_get_the_ai_english(self):
        llm = FakeLlm({"status": "ok", "output": "Come after tea.", "problems": [], "seconds": 0.5})
        room = room_with(llm, ["भैया चाय पीकर आना"])
        room.set_pref("biker", "en")
        rec = room.process("customer", WAV)
        self.assertEqual((rec["status"], rec["dst"]), ("ai", "en"))
        self.assertEqual(llm.asked[0][1], "en")
        self.assertEqual(room.api.said[0][2], "en-IN")

    def test_the_snapshot_says_whether_the_fallback_is_on(self):
        self.assertTrue(room_with(FakeLlm(OK_KN), []).snapshot("stage")["llm"]["enabled"])
        self.assertFalse(connected([]).snapshot("stage")["llm"]["enabled"])

    def test_with_the_ai_on_a_small_fragment_from_the_rules_is_not_spoken(self):
        rejected = {"status": "rejected", "output": "x", "problems": ["number: ['2'] said but not in the output"], "seconds": 0.5}
        room = room_with(FakeLlm(rejected), ["भैया मैं पांच मिनट में आ रहा हूँ"])           # the rules understand 2 of 4 content words
        rec = room.process("customer", WAV)
        self.assertLess(rec["coverage"], 0.9)
        self.assertEqual((rec["status"], rec["reason"], rec["rules_status"]), ("untranslated", "low_coverage", "partial"))
        self.assertEqual(rec["output"], "")
        self.assertEqual(len(rec["notices"]), 1)                                           # both people are told, as for any refusal
        self.assertNotIn("ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", " ".join(t for t, _, _ in room.api.said))

    def test_with_the_ai_on_a_mostly_understood_sentence_is_still_spoken_by_the_rules(self):
        rejected = {"status": "rejected", "output": "x", "problems": ["colour"], "seconds": 0.5}
        text = "भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ यार"
        room = room_with(FakeLlm(rejected), [text])
        rec = room.process("customer", WAV)
        self.assertGreaterEqual(rec["coverage"], 0.9)
        self.assertEqual(rec["status"], "partial")                                         # 12 of 13 content words understood: spoken, with the notice
        self.assertIn("ನೇರವಾಗಿ ಬನ್ನಿ", rec["output"])

    def test_without_the_ai_the_partial_translation_is_unchanged(self):
        room = connected(["भैया मैं पांच मिनट में आ रहा हूँ"])
        rec = room.process("customer", WAV)
        self.assertEqual((rec["status"], rec["output"]), ("partial", "ನಾನು ಬರುತ್ತಿದ್ದೇನೆ"))     # off by default: the recorded demo does not change

    def test_an_english_gloss_with_a_gap_is_not_shown(self):
        room = room_with(FakeLlm(OK_KN, gloss="Come [unclear] tea"), ["भैया चाय पीकर आना"])
        self.assertEqual(room.process("customer", WAV)["english"], "(AI translation; no English gloss)")

    def test_without_the_fallback_a_run_is_exactly_as_before(self):
        room = connected(["भैया चाय पीकर आना"])
        rec = room.process("customer", WAV)
        self.assertEqual((rec["status"], rec["ai"]), ("untranslated", None))
        self.assertNotIn("llm", rec["ms"])


class TestReplay(unittest.TestCase):
    DEMO = os.path.join(ROOT, "demos", "realistic_call_10db.json")

    def test_it_answers_only_what_was_recorded_and_says_so(self):
        r = llm_fallback.ReplayLlm(self.DEMO)
        a = r.translate("हेलो भैया आप कहाँ हो", "kn-IN")
        self.assertEqual((a["status"], a["replayed"]), ("ok", True))
        self.assertIn("ಎಲ್ಲಿ", a["output"])
        miss = r.translate("something nobody recorded", "kn-IN")
        self.assertEqual((miss["status"], miss["replayed"]), ("error", True))
        self.assertEqual(r.translate("हेलो भैया आप कहाँ हो", "en")["status"], "error")           # a different target was not recorded either

    def test_a_kannada_reply_is_replayed_for_the_customer(self):
        a = llm_fallback.ReplayLlm(self.DEMO).translate("ಸರಿ ಅಣ್ಣ ಬರ್ತಾಯಿದ್ದೀನಿ", "hi-IN", "kn-IN")
        self.assertEqual((a["status"], a["output"]), ("ok", "ठीक है, भाई आ रहा हूँ।"))

    def test_the_check_still_runs_on_a_replayed_answer(self):
        import tempfile
        rec = {"turns": [{"src": "hi-IN", "dst": "en", "heard": "दो गली बाद राइट ले लो", "english": "", "ai": {"output": "Turn right after that lane.", "seconds": 1.0}}]}
        f = os.path.join(tempfile.mkdtemp(), "r.json")
        json.dump(rec, open(f, "w"))
        self.assertEqual(llm_fallback.ReplayLlm(f).translate("दो गली बाद राइट ले लो", "en")["status"], "rejected")
        self.assertEqual(llm_fallback.ReplayLlm(f, guard_on=False).translate("दो गली बाद राइट ले लो", "en")["status"], "ok")

    def test_every_ai_turn_of_the_saved_call_passes_the_check_when_replayed(self):
        data = json.load(open(self.DEMO, encoding="utf-8"))
        r = llm_fallback.ReplayLlm(self.DEMO)
        ai_turns = [t for t in data["turns"] if t.get("ai")]
        self.assertGreaterEqual(len(ai_turns), 4)
        for t in ai_turns:
            self.assertEqual(r.translate(t["heard"], t["dst"], t["src"])["status"], "ok", t["heard"])

    def test_the_relay_marks_a_replayed_turn_so_the_screen_can_say_so(self):
        room = room_with(llm_fallback.ReplayLlm(self.DEMO), ["हेलो भैया आप कहाँ हो"])
        bike = room.subscribe("biker"); drain(bike)
        rec = room.process("customer", WAV)
        self.assertEqual(rec["status"], "ai")
        self.assertTrue(rec["ai"]["replayed"])
        self.assertTrue(drain(bike)[0]["replayed"])
        self.assertTrue(room.snapshot("stage")["llm"]["replay"])

    def test_the_saved_demo_has_its_speaker_clips(self):
        import zlib
        import live_call
        for step in live_call.SCRIPT_REAL:
            p = live_call.ROLES[step["who"]]
            key = "|".join((p["voice"], p["lang"], step["text"]))
            self.assertTrue((Path(ROOT) / "demos" / "clips" / f"{zlib.crc32(key.encode()):08x}.wav").exists(), step["text"])


if __name__ == "__main__":
    unittest.main()
