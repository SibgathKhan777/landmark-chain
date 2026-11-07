"""The call where the customer speaks English and the biker speaks Hindi: the English rules, and the relay with the languages swapped."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gnani  # noqa: E402
import live_call  # noqa: E402
from live_call import CallRoom  # noqa: E402
from test_live import FakeLive, WAV, drain  # noqa: E402
from translate import translate  # noqa: E402

TR, PA, NO = "translated", "partial", "untranslated"
# (English said by the customer, status, Hindi the biker hears or reason when refused)
EN_CASES = [
    ("Go straight, take a right, then you will see a building ahead. Wait there.", TR, "सीधे जाइए, दाएं मुड़िए, सामने बिल्डिंग दिखेगी, वहाँ रुकिए"),
    ("go straight and take a left", TR, "सीधे जाइए, बाएं मुड़िए"),
    ("come straight", TR, "सीधे आइए"),
    ("turn left", TR, "बाएं मुड़िए"),
    ("you will see a blue gate ahead", TR, "सामने नीला गेट दिखेगा"),
    ("Yes, that is right.", TR, "हाँ, सही है"),                       # "right" here is agreement, not a turn
    ("Right here, wait.", TR, "यहाँ रुकिए"),                           # "right here" is not a turn either
    ("I could not find it", TR, "नहीं मिला"),
    ("Wait there, I will be down in five minutes.", PA, "वहाँ रुकिए"),
    ("Do not turn right, go straight.", NO, "negation"),
    ("Should I go straight?", NO, "question"),
    ("If you see the temple turn left.", NO, "condition"),
    ("Turn left at the second lane.", NO, "distance"),
    ("Go straight for two hundred meters.", NO, "distance"),
    ("The driver will wait, go straight.", NO, "third_person"),
    ("Take a right, then take a left.", TR, "दाएं मुड़िए, बाएं मुड़िए"),
    ("Take a right and then a left.", NO, "conflict"),                 # a limit: the second "left" has no verb of its own, so it is refused rather than guessed
    ("Turn right left.", NO, "conflict"),
    ("Please bring some water.", NO, "no_known_words"),
]


class TestEnglishRules(unittest.TestCase):
    def test_cases(self):
        for text, status, want in EN_CASES:
            r = translate(text, "en", "hi-IN")
            self.assertEqual(r.status, status, text)
            self.assertEqual(r.output if status != NO else r.reason, want, text)

    def test_a_clause_never_swallows_the_words_after_it(self):
        # "wait there" follows "a building ahead": it must come out as its own instruction, not be eaten as part of what is seen
        r = translate("you will see a building ahead wait there", "en", "hi-IN")
        self.assertEqual(r.output, "सामने बिल्डिंग दिखेगी, वहाँ रुकिए")
        r = translate("you will see a building and then something else", "en", "hi-IN")
        self.assertEqual(r.status, PA)                                     # the rest is announced, not dropped

    def test_a_refusal_is_announced_in_the_right_languages(self):
        r = translate("Do not turn right", "en", "hi-IN")
        self.assertEqual(r.status, NO)
        self.assertIn("This could not be translated", r.notice_to_speaker)       # to the English speaker, in English
        self.assertIn("अनुवाद", r.notice_to_listener)                            # to the Hindi listener, in Hindi

    def test_the_hindi_to_english_direction_is_unchanged(self):
        self.assertEqual(translate("बिल्डिंग दिख गई भैया", "hi-IN", "en").output, "I can see the building")
        self.assertEqual(translate("मैं आ रहा हूँ", "hi-IN", "en").output, "I am coming")


class TestEnglishCall(unittest.TestCase):
    def room(self, transcripts, **kw):
        room = CallRoom(FakeLive(transcripts), sleep=lambda s: None, **kw)
        room.start_call("en")
        room.answer()
        return room

    def test_the_languages_follow_the_script(self):
        self.assertEqual(live_call.SCRIPT_ROLES["english"], "en")
        self.assertEqual(live_call.SCRIPT_ROLES["default"], "kn")
        self.assertEqual(live_call.ROLES_EN["customer"]["language"], "English")
        self.assertEqual(live_call.ROLES_EN["biker"]["language"], "Hindi")

    def test_prisma_is_asked_for_english_and_for_hindi(self):
        asked = []

        class Api(FakeLive):
            def stt(self, wav, lang):
                asked.append(lang)
                return "go straight"

        room = CallRoom(Api(), sleep=lambda s: None)
        room.start_call("en")
        room.answer()
        room.process("customer", WAV)
        room.process("biker", WAV)
        self.assertEqual(asked, ["en-IN", "hi-IN"])

    def test_each_window_gets_only_its_own_language(self):
        room = self.room(["Go straight, take a right"])
        cust, bike = room.subscribe("customer"), room.subscribe("biker")
        drain(cust); drain(bike)
        rec = room.process("customer", WAV)
        c, b = drain(cust), drain(bike)
        self.assertEqual(rec["status"], TR)
        self.assertEqual(b[0]["lang"], "hi-IN")
        self.assertEqual(b[0]["text"], "सीधे जाइए, दाएं मुड़िए")
        self.assertNotIn("straight", json.dumps(b, ensure_ascii=False))      # the English never reaches the biker's window
        self.assertEqual(c[0]["text"], "Go straight, take a right")
        text, voice, lang = room.api.said[0]
        self.assertEqual(lang, "hi-IN")                                       # the interpreter speaks Hindi to the biker

    def test_the_biker_is_translated_into_spoken_english(self):
        room = self.room(["बिल्डिंग दिख गई भैया"])
        rec = room.process("biker", WAV)
        self.assertEqual((rec["src"], rec["dst"]), ("hi-IN", "en"))
        self.assertEqual(rec["output"], "I can see the building")
        self.assertEqual(room.api.said[0][2], "en-IN")                        # Timbre speaks the interpreter's English as en-IN

    def test_the_snapshot_and_call_events_say_who_speaks_what(self):
        room = CallRoom(FakeLive(), sleep=lambda s: None)
        q = room.subscribe("customer")
        self.assertEqual(drain(q)[0]["roles"]["customer"]["language"], "Hindi")      # before any call: the default pair
        room.start_call("en")
        ev = [e for e in drain(q) if e["type"] == "call"][0]
        self.assertEqual((ev["roles"]["customer"]["language"], ev["roles"]["biker"]["language"]), ("English", "Hindi"))
        room.end_call()
        room.start_call()                                                           # the next call is the default pair again
        ev = [e for e in drain(q) if e["type"] == "call"][-1]
        self.assertEqual(ev["roles"]["biker"]["language"], "Kannada")

    def test_the_ai_is_not_asked_for_a_language_it_has_no_prompt_for(self):
        class Boom:
            guard_on = True

            def translate(self, *a, **k):
                raise AssertionError("the AI has no English-to-Hindi route and must not be asked")

        room = CallRoom(FakeLive(["Wait there, I will be down in five minutes."]), sleep=lambda s: None, llm=Boom())
        room.start_call("en")
        room.answer()
        rec = room.process("customer", WAV)
        self.assertEqual(rec["status"], PA)                                    # the rules' partial stands: the coverage rule only applies where the AI could help
        self.assertEqual(rec["output"], "वहाँ रुकिए")

    def test_the_whole_script_runs(self):
        room = CallRoom(FakeLive(["go straight take a right then you will see a building ahead wait there", "बिल्डिंग दिख गई भैया",
                                  "wait there i will be down in five minutes", "please drink some water"]), sleep=lambda s: None)
        orig = room.make_clip
        room.make_clip = lambda step, n, earlier: (gnani.write_wav([100] * 1600, 16000), gnani.write_wav([100] * 1600, 16000))
        room.play_script(live_call.SCRIPTS["english"], roles="en")
        self.assertEqual([h["status"] for h in room.history], [TR, TR, PA, NO])
        self.assertEqual([h["who"] for h in room.history], ["customer", "biker", "customer", "customer"])
        self.assertIsNotNone(orig)


if __name__ == "__main__":
    unittest.main()
