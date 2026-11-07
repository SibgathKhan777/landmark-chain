import itertools
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import translate as T  # noqa: E402
from extraction import CRITICAL, extract  # noqa: E402
from translate import intents, render, translate  # noqa: E402

ANCHORS = list(T.HI_ANCHOR)
RELS = list(T.HI_REL)
COLOURS = list(T.KN_COLOUR)


def crit(slots):
    return {k: set(slots[k]) for k in CRITICAL if slots[k]}


def want(**kw):
    return {k: ({v} if isinstance(v, str) else set(v)) for k, v in kw.items()}


class TestRoundTrip(unittest.TestCase):
    """Everything the tables can write must be read back to the same slots by the extractor."""

    def check(self, slots, lang):
        phrase = render(slots, lang)
        self.assertIsNotNone(phrase, (slots, lang))
        got = extract(phrase)
        self.assertEqual(crit(got), crit({k: frozenset(v) for k, v in slots.items()} | {k: frozenset() for k in CRITICAL if k not in slots}), (phrase, lang))
        if not (lang == "kn-IN" and "TEA_STALL" in slots.get("anchor", ())):      # Kannada 'tea shop' contains the word for shop
            self.assertEqual(set(got["target"]), set(slots.get("target", ())), (phrase, lang))

    def test_anchor_relation_colour_target(self):
        for lang, a, r, c, t in itertools.product(("hi-IN", "kn-IN"), ANCHORS, RELS, COLOURS, ("GATE", "HOUSE")):
            with self.subTest(lang=lang, a=a, r=r, c=c, t=t):
                self.check({"anchor": {a}, "relation": {r}, "colour": {c}, "target": {t}}, lang)

    def test_anchor_relation_alone(self):
        for lang, a, r in itertools.product(("hi-IN", "kn-IN"), ANCHORS, RELS):
            with self.subTest(lang=lang, a=a, r=r):
                self.check({"anchor": {a}, "relation": {r}}, lang)

    def test_side_ordinal_target(self):
        for lang, side, o, t in itertools.product(("hi-IN", "kn-IN"), ("LEFT", "RIGHT"), ("1", "2", "3", "4", "5"), ("GATE", "SHOP", "HOUSE")):
            with self.subTest(lang=lang, side=side, o=o, t=t):
                self.check({"side": {side}, "ordinal": {o}, "target": {t}}, lang)

    def test_lane_and_house(self):
        for lang, o, c in itertools.product(("hi-IN", "kn-IN"), ("1", "2", "3"), ("GREEN", "YELLOW", "BLUE")):
            with self.subTest(lang=lang, o=o, c=c):
                self.check({"ordinal": {o}, "colour": {c}, "target": {"LANE", "HOUSE"}}, lang)

    def test_hanuman_temple(self):
        for lang in ("hi-IN", "kn-IN"):
            self.check({"anchor": {"HANUMAN", "TEMPLE"}, "relation": {"BEHIND"}, "colour": {"RED"}, "target": {"GATE"}}, lang)

    def test_everything_the_tables_write_translates_cleanly_when_fed_back_in(self):
        """A phrase the translator produced must not come back as 'partly translated' or refused."""
        other = {"hi-IN": "kn-IN", "kn-IN": "hi-IN"}
        for lang, a, r in itertools.product(("hi-IN", "kn-IN"), ANCHORS, RELS):
            for slots in ({"anchor": {a}, "relation": {r}}, {"anchor": {a}, "relation": {r}, "colour": {"RED"}, "target": {"GATE"}}):
                phrase = render(slots, lang)
                with self.subTest(lang=lang, phrase=phrase):
                    res = translate(phrase, lang, other[lang])
                    self.assertEqual((res.status, res.untranslated), ("translated", []))

    def test_intent_phrases_are_recognised_again(self):
        for lang in ("hi-IN", "kn-IN"):
            for name, text in T.INTENT_TEXT[lang].items():
                with self.subTest(lang=lang, intent=name):
                    self.assertEqual(intents(text, lang)[0], [name])

    def test_unsupported_combinations_return_none(self):
        self.assertIsNone(render({"relation": {"STRAIGHT"}, "anchor": {"BUS_STAND"}}, "kn-IN"))
        self.assertIsNone(render({"colour": {"BLUE", "RED"}, "target": {"GATE"}}, "hi-IN"))
        self.assertIsNone(render({"ordinal": {"2"}}, "kn-IN"))                  # an ordinal needs a noun
        self.assertIsNone(render({}, "hi-IN"))


class TestInterpreter(unittest.TestCase):
    def test_the_example_from_the_brief(self):
        for said in ("भैया ये गेट दूसरा गेट दायीं तरफ वाला", "bhaiya ye gate dusra gate daayi side wala", "bhaiya dusra gate right side wala"):
            with self.subTest(said=said):
                r = translate(said, "hi-IN", "kn-IN")
                self.assertEqual((r.status, r.output, r.english), ("translated", "ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್", "second gate on the right"))

    def test_kannada_back_to_hindi(self):
        r = translate("ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್", "kn-IN", "hi-IN")
        self.assertEqual((r.status, r.output), ("translated", "दाएं तरफ दूसरा गेट"))
        self.assertEqual(translate("ದೇವಸ್ಥಾನದ ಹಿಂದಿನ ನೀಲಿ ಗೇಟ್", "kn-IN", "hi-IN").output, "मंदिर के पीछे नीला गेट")

    def test_kannada_inflections_and_zero_width_joiners(self):
        self.assertEqual(translate("ಟ್ಯಾಂಕಿನ ಹತ್ತಿರದ ಹಳದಿ ಮನೆ", "kn-IN", "hi-IN").output, "पानी की टंकी के पास पीला मकान")
        self.assertEqual(translate("ಸರ್ಕಲ್‌ನ ಹಿಂದೆ", "kn-IN", "hi-IN").output, "चौक के पीछे")

    def test_closed_phrasebook(self):
        for said, src, dst, out in [("हाँ, सही है", "hi-IN", "kn-IN", "ಹೌದು, ಸರಿ"), ("नहीं मिला", "hi-IN", "kn-IN", "ಸಿಗಲಿಲ್ಲ"),
                                    ("मिल गया", "hi-IN", "kn-IN", "ಸಿಕ್ಕಿತು"), ("ಸಿಕ್ಕಿತು", "kn-IN", "hi-IN", "मिल गया"),
                                    ("ಸಿಗಲಿಲ್ಲ", "kn-IN", "hi-IN", "नहीं मिला"), ("ಹೌದು", "kn-IN", "hi-IN", "हाँ, सही है"),
                                    ("दोबारा बोलिए", "hi-IN", "kn-IN", "ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ")]:
            with self.subTest(said=said):
                r = translate(said, src, dst)
                self.assertEqual((r.status, r.output), ("translated", out))

    def test_intent_and_landmark_in_one_message(self):
        self.assertEqual(translate("हाँ, दूसरा गेट", "hi-IN", "kn-IN").output, "ಹೌದು, ಸರಿ, ಎರಡನೇ ಗೇಟ್")
        self.assertEqual(translate("दूसरा गेट नहीं मिला", "hi-IN", "kn-IN").output, "ಎರಡನೇ ಗೇಟ್, ಸಿಗಲಿಲ್ಲ")

    def test_several_landmarks_in_order(self):
        r = translate("मंदिर के पीछे, फिर दूसरी गली में हरा मकान", "hi-IN", "kn-IN")
        self.assertEqual(r.output, "ದೇವಸ್ಥಾನದ ಹಿಂದೆ, ಎರಡನೇ ಗಲ್ಲಿಯ ಹಸಿರು ಮನೆ")

    def test_free_conversation_is_refused_and_says_so(self):
        r = translate("भैया चाय पीकर आना", "hi-IN", "kn-IN")
        self.assertEqual((r.status, r.output, r.reason), ("untranslated", "", "no_known_words"))
        self.assertEqual(r.untranslated, ["चाय", "पीकर", "आना"])
        self.assertTrue(r.notice_to_speaker and r.notice_to_listener)
        self.assertIn("अनुवाद", r.notice_to_speaker)                 # told to the speaker in the speaker's language
        self.assertIn("ಅನುವಾದ", r.notice_to_listener)               # and to the listener in theirs

    def test_negation_is_refused_not_guessed(self):
        r = translate("नीला गेट नहीं, लाल गेट", "hi-IN", "kn-IN")
        self.assertEqual((r.status, r.reason), ("untranslated", "negation"))
        self.assertEqual(translate("ನೀಲಿ ಗೇಟ್ ಅಲ್ಲ, ಇಲ್ಲ", "kn-IN", "hi-IN").status, "untranslated")

    def test_two_values_at_once_are_refused(self):
        self.assertEqual(translate("नीला लाल गेट", "hi-IN", "kn-IN").reason, "ambiguous")
        self.assertEqual(translate("हाँ नहीं", "hi-IN", "kn-IN").reason, "ambiguous_answer")
        self.assertEqual(translate("मंदिर के पीछे मस्जिद के पास", "hi-IN", "kn-IN").reason, "several_landmarks")

    def test_directions_are_not_supported(self):
        r = translate("बस स्टैंड से सीधे जाकर दाएं मुड़िए", "hi-IN", "kn-IN")
        self.assertEqual((r.status, r.reason), ("untranslated", "unsupported_combination"))

    def test_partial_translation_keeps_the_landmark_and_flags_the_rest(self):
        r = translate("भैया मैं पांच मिनट में आ रहा हूँ दूसरा गेट दायीं तरफ", "hi-IN", "kn-IN")
        self.assertEqual((r.status, r.output), ("partial", "ನಾನು ಬರುತ್ತಿದ್ದೇನೆ, ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್"))   # "I am coming" is a plan the grammar knows
        self.assertEqual(r.untranslated, ["पांच", "मिनट"])               # the five minutes are not translated, and the notice says so
        self.assertIn("ಅನುವಾದ", r.notice_to_listener)                # the listener is told something was left out

    def test_words_inside_a_landmark_name_are_not_reported_as_unknown(self):
        for text in ("पानी की टंकी के पास पीला मकान", "पोस्ट ऑफिस के पीछे", "बस स्टैंड के पास", "चाय की टपरी के पास"):
            with self.subTest(text=text):
                self.assertEqual(translate(text, "hi-IN", "kn-IN").status, "translated")
        for text in ("ಬಸ್ ನಿಲ್ದಾಣದ ಹಿಂದೆ", "ಅಂಚೆ ಕಚೇರಿಯ ಹತ್ತಿರ", "ಪೆಟ್ರೋಲ್ ಬಂಕ್\u200cನ ಹತ್ತಿರ"):
            with self.subTest(text=text):
                self.assertEqual(translate(text, "kn-IN", "hi-IN").status, "translated")
        self.assertEqual(translate("भैया चाय पीकर आना", "hi-IN", "kn-IN").untranslated, ["चाय", "पीकर", "आना"])   # tea is not a tea stall

    def test_polite_filler_does_not_count_as_untranslated(self):
        self.assertEqual(translate("भैया दूसरा गेट दायीं तरफ वाला", "hi-IN", "kn-IN").status, "translated")

    def test_every_refusal_has_a_plain_reason(self):
        for text in ["चाय पीकर आना", "नीला लाल गेट", "नीला गेट नहीं"]:
            r = translate(text, "hi-IN", "kn-IN")
            self.assertTrue(r.reason_text, text)

    def test_english_meaning_is_provided(self):
        self.assertEqual(translate("मंदिर के पीछे नीला गेट", "hi-IN", "kn-IN").english, "blue gate behind the temple")
        self.assertEqual(translate("दूसरी गली में हरा मकान", "hi-IN", "kn-IN").english, "green house in the second lane")



class TestLimits(unittest.TestCase):
    def test_every_documented_limit_is_really_refused_for_the_stated_reason(self):
        for title, text, lang, reason in T.LIMITS:
            with self.subTest(limit=title):
                r = translate(text, lang, "kn-IN" if lang == "hi-IN" else "hi-IN")
                self.assertEqual((r.status, r.reason), ("untranslated", reason))
                self.assertEqual(r.output, "")
                self.assertTrue(r.notice_to_speaker and r.notice_to_listener)

    def test_vocabulary_counts_match_the_tables(self):
        c = T.vocabulary_counts()
        self.assertEqual(c["colours"], len(T.HI_COLOUR["m"]))
        self.assertEqual(c["relations"], len(T.HI_REL))
        self.assertEqual(c["landmark types"], len(T.HI_ANCHOR) + 1)        # plus the Hanuman temple
        self.assertEqual(set(T.KN_TARGET), set(T.HI_TARGET))


if __name__ == "__main__":
    unittest.main()
