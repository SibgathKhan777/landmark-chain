import unittest

import directions
from translate import LIMITS, translate

SENTENCE = "भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी, वहाँ ठहरो मैं आ रहा हूँ।"     # what Prisma returns for the call sentence


class TestDirections(unittest.TestCase):
    def test_the_whole_call_sentence_in_kannada(self):
        r = translate(SENTENCE, "hi-IN", "kn-IN")
        self.assertEqual(r.status, "translated")
        self.assertEqual(r.output, "ನೇರವಾಗಿ ಬನ್ನಿ, ಬಲಕ್ಕೆ ತಿರುಗಿ, ಎದುರು ಕಟ್ಟಡ ಕಾಣಿಸುತ್ತದೆ, ಅಲ್ಲಿ ನಿಲ್ಲಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ")
        self.assertEqual(r.clauses, ["STRAIGHT", "TURN", "SEE_AHEAD", "WAIT", "COMING"])
        self.assertEqual(r.untranslated, [])

    def test_the_whole_call_sentence_in_english(self):
        r = translate(SENTENCE, "hi-IN", "en")
        self.assertEqual(r.output, "come straight, turn right, you will see a building ahead, wait there, I am coming")
        self.assertEqual(r.english, r.output)

    def test_roman_hinglish_gives_the_same_clauses(self):
        r = translate("Bhaiya seedhe aa jao right hojao phir samne building dikhegi wahan thehro main aa raha hoon", "hi-IN", "kn-IN")
        self.assertEqual((r.status, r.clauses), ("translated", ["STRAIGHT", "TURN", "SEE_AHEAD", "WAIT", "COMING"]))

    def test_each_turn_and_each_straight_verb(self):
        for text, want in (("दाएं मुड़िए", "ಬಲಕ್ಕೆ ತಿರುಗಿ"), ("बाएं मुड़ो", "ಎಡಕ್ಕೆ ತಿರುಗಿ"), ("लेफ्ट ले लो", "ಎಡಕ್ಕೆ ತಿರುಗಿ"),
                           ("सीधे चलो", "ನೇರವಾಗಿ ಹೋಗಿ"), ("सीधे आइए", "ನೇರವಾಗಿ ಬನ್ನಿ"), ("यहाँ रुको", "ಇಲ್ಲಿ ನಿಲ್ಲಿ")):
            with self.subTest(text=text):
                r = translate(text, "hi-IN", "kn-IN")
                self.assertEqual((r.status, r.output), ("translated", want))

    def test_what_is_seen_can_carry_a_colour_and_a_number(self):
        r = translate("सामने दूसरा नीला गेट दिखेगा", "hi-IN", "kn-IN")
        self.assertEqual((r.status, r.output), ("translated", "ಎದುರು ಎರಡನೇ ನೀಲಿ ಗೇಟ್ ಕಾಣಿಸುತ್ತದೆ"))
        self.assertEqual(translate("सामने नीला गेट दिखेगा", "hi-IN", "en").output, "you will see a blue gate ahead")

    def test_a_time_is_left_out_and_the_listener_is_told(self):
        r = translate("सीधे आ जाओ मैं पांच मिनट में आ रहा हूँ", "hi-IN", "kn-IN")
        self.assertEqual(r.status, "partial")
        self.assertEqual(r.output, "ನೇರವಾಗಿ ಬನ್ನಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ")
        self.assertEqual(r.untranslated, ["पांच", "मिनट"])
        self.assertTrue(r.notice_to_listener)

    def test_a_clause_next_to_a_landmark_phrase(self):
        r = translate("दूसरा गेट दायीं तरफ वाला, वहाँ ठहरो", "hi-IN", "kn-IN")
        self.assertEqual(r.output, "ಅಲ್ಲಿ ನಿಲ್ಲಿ, ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್")
        self.assertEqual(r.status, "translated")

    def test_negation_and_questions_are_refused_because_they_would_flip_the_meaning(self):
        for text, why in (("दाएं मत मुड़ना सीधे आ जाओ", "negation"), ("सीधे नहीं जाना है बाएं मुड़ो", "negation"),
                          ("क्या सीधे आ जाऊं", "question"), ("सीधे आ जाओ?", "question")):
            with self.subTest(text=text):
                r = translate(text, "hi-IN", "kn-IN")
                self.assertEqual((r.status, r.reason), ("untranslated", why))
                self.assertEqual(r.output, "")

    def test_two_opposite_turns_are_refused_unless_something_sequences_them(self):
        self.assertEqual(translate("राइट ले लो लेफ्ट ले लो", "hi-IN", "kn-IN").reason, "conflict")
        r = translate("दाएं मुड़ो फिर बाएं मुड़ो", "hi-IN", "kn-IN")          # "then" between them makes it a route, not a conflict
        self.assertEqual((r.status, r.output), ("translated", "ಬಲಕ್ಕೆ ತಿರುಗಿ, ಎಡಕ್ಕೆ ತಿರುಗಿ"))

    def test_a_side_word_without_a_turn_verb_is_still_just_a_landmark_side(self):
        r = translate("दूसरा गेट दायीं तरफ वाला", "hi-IN", "kn-IN")
        self.assertEqual((r.output, r.clauses), ("ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್", []))

    def test_the_rider_can_answer_in_kannada(self):
        for text, hindi, english in (("ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", "वे आ रहे हैं", "I am coming"),
                                     ("ನಾನು ಇಲ್ಲಿ ನಿಂತಿದ್ದೇನೆ", "वे यहाँ खड़े हैं", "I am standing here"),
                                     ("ಕಟ್ಟಡ ಕಾಣಿಸಿತು", "बिल्डिंग दिख गई", "I can see the building")):
            with self.subTest(text=text):
                self.assertEqual(translate(text, "kn-IN", "hi-IN").output, hindi)
                self.assertEqual(translate(text, "kn-IN", "en").output, english)

    def test_a_place_is_only_written_when_it_was_said(self):
        # real Prisma output for "OK, I am standing near the building": "near the building" is not translated, and "here" was never said
        r = translate("ಸರಿ ನಾನು ಕಟ್ಟಡದ ಹತ್ತಿರ ನಿಂತಿದ್ದೇನೆ", "kn-IN", "en")
        self.assertEqual(r.status, "partial")
        self.assertIn("I am standing", r.output)
        self.assertNotIn("here", r.output)
        self.assertEqual(translate("ನಾನು ಇಲ್ಲಿ ನಿಂತಿದ್ದೇನೆ", "kn-IN", "en").output, "I am standing here")
        self.assertEqual(translate("मैं खड़ा हूँ", "hi-IN", "kn-IN").output, "ನಾನು ನಿಂತಿದ್ದೇನೆ")

    def test_hindi_never_guesses_the_speakers_gender(self):
        out = translate("ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", "kn-IN", "hi-IN").output
        self.assertNotIn("रहा हूँ", out)
        self.assertNotIn("रही हूँ", out)

    def test_kannada_directions_are_not_understood_only_the_riders_replies_are(self):
        r = translate("ನೇರವಾಗಿ ಬನ್ನಿ ಬಲಕ್ಕೆ ತಿರುಗಿ", "kn-IN", "hi-IN")
        self.assertEqual((r.status, r.clauses), ("untranslated", []))

    def test_every_clause_can_be_written_in_every_language(self):
        np = {"colour": set(), "ordinal": set(), "target": {"BUILDING"}, "anchor": set(), "relation": set(), "side": set()}
        clauses = [{"act": "STRAIGHT", "verb": "come"}, {"act": "STRAIGHT", "verb": "go"}, {"act": "TURN", "side": "RIGHT"},
                   {"act": "TURN", "side": "LEFT"}, {"act": "WAIT", "place": "THERE"}, {"act": "WAIT", "place": "HERE"},
                   {"act": "WAIT", "place": None}, {"act": "COMING"}, {"act": "STANDING"},
                   {"act": "SEE_AHEAD", "slots": np}, {"act": "SEEN", "slots": np}]
        for c in clauses:
            for lang in ("hi-IN", "kn-IN", "en"):
                with self.subTest(clause=c["act"], lang=lang):
                    self.assertTrue(directions.render(c, lang))

    def test_no_clause_means_the_old_landmark_path_is_untouched(self):
        self.assertEqual(translate("भैया ये गेट दूसरा गेट दायीं तरफ वाला", "hi-IN", "kn-IN").output, "ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್")
        self.assertEqual(translate("हाँ, सही है", "hi-IN", "kn-IN").output, "ಹೌದು, ಸರಿ")

    def test_english_output_has_its_own_notices(self):
        r = translate("भैया चाय पीकर आना", "hi-IN", "en")
        self.assertEqual(r.status, "untranslated")
        self.assertTrue(r.notice_to_listener.isascii())

    def test_every_limit_still_refused_for_its_stated_reason(self):
        for name, text, lang, reason in LIMITS:
            with self.subTest(name=name):
                self.assertEqual(translate(text, lang, "kn-IN" if lang == "hi-IN" else "hi-IN").reason, reason)


if __name__ == "__main__":
    unittest.main()
