import json
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import guard  # noqa: E402

RUN = json.loads((Path(ROOT) / "tests" / "fixtures" / "evon_q5_examples.json").read_text(encoding="utf-8"))
BY_SAID = {r["said"]: r for r in RUN["results"]}


def kn(src):
    return BY_SAID[src]["Kannada_direct"]["text"]


def en(src):
    return BY_SAID[src]["English"]["text"]


class TestGuardOnTheRealEvonRun(unittest.TestCase):
    """tests/fixtures/evon_q5_examples.json is what Evon returned on Kaggle (the second Kaggle run that produced translations, with examples in the prompt and the 5-bit file; 18 sentences). The guard was written AFTER seeing its
    mistakes, so these results are in-sample: they show the known mistakes are caught, not how often unseen ones are."""

    def test_the_left_right_swap_is_caught(self):
        src = "bhaiya second gate right side wala, uske upar blue board hai"
        self.assertIn("side", " ".join(guard.check(src, en(src), "en")))
        self.assertEqual(guard.check(src, kn(src), "kn-IN"), [])                 # the direct Kannada route said "right" correctly

    def test_the_dropped_count_is_caught_in_both_languages(self):
        src = "do gali baad building ke samne ruko"
        for out, dst in ((en(src), "en"), (kn(src), "kn-IN")):
            self.assertTrue(any("number" in p for p in guard.check(src, out, dst)), out)

    def test_the_other_direct_kannada_outputs_all_pass(self):
        rejected = {r["said"] for r in RUN["results"] if guard.check(r["said"], r["Kannada_direct"]["text"], "kn-IN")}
        self.assertEqual(rejected, {"do gali baad building ke samne ruko"})

    def test_the_english_outputs_rejected_are_exactly_the_three_with_a_real_difference(self):
        rejected = {r["said"][:20] for r in RUN["results"] if guard.check(r["said"], r["English"]["text"], "en")}
        self.assertEqual(len(rejected), 3)                                       # side swap, dropped count, and a paraphrase that added "until"


class TestGuardCatchesEachKindOfChange(unittest.TestCase):
    def test_side(self):
        s = "दो गली बाद राइट ले लो"
        self.assertEqual(guard.check(s, "ಎರಡು ಗಲ್ಲಿಯ ನಂತರ ಬಲಕ್ಕೆ ತಿರುಗಿ.", "kn-IN"), [])
        self.assertTrue(guard.check(s, "ಎರಡು ಗಲ್ಲಿಯ ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ.", "kn-IN"))
        self.assertTrue(guard.check(s, "Turn left after two lanes.", "en"))
        self.assertEqual(guard.check(s, "Turn right after two lanes.", "en"), [])

    def test_negation_in_both_directions(self):
        s = "left mat lo seedha jao"
        self.assertEqual(guard.check(s, "ಎಡಕ್ಕೆ ತಿರುಗಬೇಡ, ನೇರವಾಗಿ ಹೋಗು.", "kn-IN"), [])
        self.assertTrue(guard.check(s, "ಎಡಕ್ಕೆ ತಿರುಗಿ, ನೇರವಾಗಿ ಹೋಗು.", "kn-IN"))           # "do not" lost
        self.assertTrue(guard.check("seedha jao", "Do not go straight.", "en"))              # "do not" invented
        self.assertEqual(guard.check(s, "Don't turn left, go straight.", "en"), [])

    def test_a_here_in_kannada_is_not_mistaken_for_a_no(self):
        # "ಇಲ್ಲಿ" (here) starts with the letters of "ಇಲ್ಲ" (no): it must not count as a negation
        self.assertEqual(guard.check("yahan ruko", "ಇಲ್ಲಿ ನಿಲ್ಲಿ.", "kn-IN"), [])

    def test_question(self):
        self.assertEqual(guard.check("kya yahan ruk jaun", "ನಾನು ಇಲ್ಲಿ ನಿಲ್ಲಬೇಕೇ?", "kn-IN"), [])
        self.assertTrue(guard.check("kya yahan ruk jaun", "ನಾನು ಇಲ್ಲಿ ನಿಲ್ಲಬೇಕು.", "kn-IN"))
        self.assertTrue(guard.check("yahan ruko", "Should I stop here?", "en"))

    def test_a_question_word_is_enough_without_a_question_mark(self):
        # real answers from the live test: Evon wrote the content question with a full stop, which is a fine translation
        for src, out in (("हेलो भैया मैं इधर ऊपर खड़ा हूँ कहाँ हो आप", "ಹಲೋ ಅಣ್ಣಾ ನಾನು ಇಲ್ಲಿಯೇ ಮೇಲೆ ನಿಂತಿದ್ದೇನೆ, ನೀವು ಎಲ್ಲಿದ್ದೀರಿ."),
                         ("हेलो भैया, कहाँ हो मैं इधर ऊपर खड़ा हूँ, तीसरे फ्लोर पे आ जाइए।", "ಹಲೋ ಅಣ್ಣಾ, ಎಲ್ಲಿದ್ದೀರಿ ನಾನು ಇಲ್ಲಿಗೆ ಮೇಲೆ ನಿಂತಿದ್ದೇನೆ, ಮೂರನೇ ಮಹಡಿಯಲ್ಲಿ ಬನ್ನಿ.")):
            self.assertEqual(guard.check(src, out, "kn-IN"), [], out)
        self.assertEqual(guard.check("कहाँ हो आप", "Where are you", "en"), [])
        self.assertTrue(guard.check("कहाँ हो आप", "I am here.", "en"))                     # no question mark and no question word
        self.assertTrue(guard.check("seedha aao", "Where should I come?", "en"))           # a statement turned into a question

    def test_condition(self):
        s = "agar building dikhe to wahan ruko"
        self.assertEqual(guard.check(s, "ಕಟ್ಟಡ ಕಾಣಿಸಿದಾಗ ಅಲ್ಲಿ ನಿಲ್ಲಿ.", "kn-IN"), [])
        self.assertTrue(guard.check(s, "ಕಟ್ಟಡದ ಬಳಿ ನಿಲ್ಲಿ.", "kn-IN"))                    # the "if" was dropped
        self.assertTrue(guard.check(s, "Stop at the building.", "en"))

    def test_colour(self):
        s = "wo banda blue shirt mein hai"
        self.assertEqual(guard.check(s, "ಅವನು ನೀಲಿ ಅಂಗಿ ಧರಿಸಿದ್ದಾನೆ.", "kn-IN"), [])
        self.assertTrue(guard.check(s, "ಅವನು ಕೆಂಪು ಅಂಗಿ ಧರಿಸಿದ್ದಾನೆ.", "kn-IN"))
        self.assertTrue(guard.check(s, "He is wearing a red shirt.", "en"))

    def test_numbers_said_as_words_join_into_one_number(self):
        s = "बिल्डिंग नंबर सिक्स सेवन नाइन"
        for ok in ("ಕಟ್ಟಡ ಸಂಖ್ಯೆ 679", "ಕಟ್ಟಡ ಸಂಖ್ಯೆ ಆರು ಏಳು ಒಂಬತ್ತು", "ಕಟ್ಟಡ ಸಂಖ್ಯೆ ೬೭೯"):
            self.assertEqual(guard.check(s, ok, "kn-IN"), [], ok)
        self.assertTrue(guard.check(s, "ಕಟ್ಟಡ ಸಂಖ್ಯೆ 697", "kn-IN"))
        self.assertTrue(guard.check(s, "ಕಟ್ಟಡ ಸಂಖ್ಯೆ ಆರು ಏಳು", "kn-IN"))
        self.assertEqual(guard.check(s, "Building number six seven nine", "en"), [])
        self.assertEqual(guard.check(s, "Building number 679", "en"), [])

    def test_a_copy_of_the_source_or_the_wrong_script_is_rejected(self):
        s = "agar building dikhe to wahan ruko"
        self.assertTrue(any("copied" in p for p in guard.check(s, s, "en")))
        self.assertTrue(guard.check("seedha aao", "सीधे आओ", "kn-IN"))
        self.assertTrue(guard.check("seedha aao", "ನೇರವಾಗಿ ಬನ್ನಿ [unclear]", "kn-IN"))
        self.assertEqual(guard.check("seedha aao", "", "kn-IN"), ["empty output"])

    def test_who_is_standing_coming_or_where_is_checked(self):
        # the real failure from the live test: "where are you ... I am standing" came back as "where am I ... you are standing"
        src = "हाँ जी भैया कहाँ हो, मैं इधर ऊपर तीसरे फ्लोर पे खड़ा हूँ"
        swapped = "ಹೌದು ಅಣ್ಣಾ, ನಾನು ಎಲ್ಲಿದ್ದೇನೆ ಹೇಳಿ. ಮೂರನೇ ಮಹಡಿಯ ಮೇಲೆ ನಿಂತಿದ್ದೀರಿ ಅಲ್ಲವೇ?"
        problems = guard.check(src, swapped, "kn-IN")
        self.assertEqual(len([p for p in problems if p.startswith("who")]), 2, problems)
        self.assertEqual(guard.check(src, "ಹೌದು ಅಣ್ಣಾ, ನೀವು ಎಲ್ಲಿದ್ದೀರಿ? ನಾನು ಮೂರನೇ ಮಹಡಿಯಲ್ಲಿ ನಿಂತಿದ್ದೇನೆ.", "kn-IN"), [])
        self.assertTrue(guard.check(src, "Yes sir, where am I? You are standing on the third floor.", "en"))
        self.assertEqual(guard.check(src, "Yes sir, where are you? I am standing on the third floor.", "en"), [])
        self.assertEqual(guard.check("driver seedha aa raha hai", "ಚಾಲಕ ನೇರವಾಗಿ ಬರುತ್ತಿದ್ದಾನೆ.", "kn-IN"), [])    # he is coming: right
        self.assertTrue(guard.check("driver seedha aa raha hai", "ನಾನು ನೇರವಾಗಿ ಬರುತ್ತಿದ್ದೇನೆ.", "kn-IN"))      # the driver became "I"
        self.assertTrue(guard.check("main aa raha hu", "ಬರುತ್ತಿದ್ದೀರಿ", "kn-IN"))                                  # I am coming became "you are coming"

    def test_a_verb_the_check_does_not_know_is_not_checked_and_that_is_stated(self):
        # who "reaches" or "waits" is NOT checked: the output below swaps the person and the guard cannot see it
        self.assertEqual(guard.check("मैं वहाँ पहुँच गया", "ನೀವು ಅಲ್ಲಿ ತಲುಪಿದ್ದೀರಿ", "kn-IN"), [])
        self.assertIn("for three verbs only", guard.__doc__)
        self.assertIn("any other verb", guard.__doc__)


class TestGuardWithAKannadaSource(unittest.TestCase):
    """The biker speaks Kannada; the AI writes Hindi or English. The answers below are what Evon returned through the tunnel."""

    def kn(self, src, out, dst):
        return guard.check(src, out, dst, src="kn-IN")

    def test_the_real_answers_pass(self):
        for src, hi, en in (("ಎಲ್ಲಿದ್ದೀಯ ಬ್ರೋ ನಾನು ಇಲ್ಲೇ ಇದ್ದೀನಿ", "भाई, कहाँ हो तुम? मैं यहीं हूँ।", "Where are you bro? I am right here."),
                            ("ನಾನು ಗೇಟ್ ಹತ್ತಿರ ನಿಂತಿದ್ದೀನಿ ನೀವು ಎಲ್ಲಿದ್ದೀರಾ", "मैं गेट के पास खड़ा हूँ, आप कहाँ हैं?", "I am standing near the gate. Where are you?"),
                            ("ಬಲಕ್ಕೆ ತಿರುಗಿ ಎರಡು ಗಲ್ಲಿ ನಂತರ ಕಟ್ಟಡ ಸಿಗುತ್ತೆ", "दाएं मुड़िए और दो गलियों बाद बिल्डिंग मिल जाएगी।", "Turn right and after two lanes, there will be a building."),
                            ("ನಾನು ಐದು ನಿಮಿಷದಲ್ಲಿ ತಲುಪುತ್ತೇನೆ", "मैं पाँच मिनट में पहुँच जाऊँगा।", "I will reach in five minutes."),
                            ("ಇಲ್ಲಿ ಯಾರೂ ಇಲ್ಲ", "यहाँ कोई नहीं है।", "There is no one here.")):
            self.assertEqual(self.kn(src, hi, "hi-IN"), [], hi)
            self.assertEqual(self.kn(src, en, "en"), [], en)

    def test_the_people_swapped_the_way_they_were_in_the_live_failure_are_caught(self):
        src = "ಎಲ್ಲಿದ್ದೀಯ ಬ್ರೋ ನಾನು ಇಲ್ಲೇ ಇದ್ದೀನಿ"
        self.assertTrue(self.kn(src, "भाई मैं कहाँ हूँ, तुम यहीं हो।", "hi-IN"))
        src2 = "ನಾನು ಗೇಟ್ ಹತ್ತಿರ ನಿಂತಿದ್ದೀನಿ"
        self.assertTrue(self.kn(src2, "आप गेट के पास खड़े हैं", "hi-IN"))
        self.assertTrue(self.kn(src2, "You are standing near the gate.", "en"))

    def test_each_kind_of_change_is_caught_from_a_kannada_source(self):
        self.assertTrue(self.kn("ಬಲಕ್ಕೆ ತಿರುಗಿ", "बाएं मुड़िए", "hi-IN"))                                  # side
        self.assertTrue(self.kn("ಇಲ್ಲಿ ನಿಲ್ಲಬೇಡಿ", "यहाँ रुकिए", "hi-IN"))                                  # negation lost
        self.assertTrue(self.kn("ನಾನು ಇಲ್ಲಿ ನಿಲ್ಲಬೇಕೇ", "मैं यहाँ रुकूँगा", "hi-IN"))                       # question became a statement
        self.assertTrue(self.kn("ಕಟ್ಟಡ ಕಾಣಿಸಿದರೆ ನಿಲ್ಲಿ", "बिल्डिंग पर रुकिए", "hi-IN"))                  # condition lost
        self.assertTrue(self.kn("ಎರಡು ಗಲ್ಲಿ ನಂತರ ಬಲಕ್ಕೆ", "गली के बाद दाएं", "hi-IN"))                     # count lost
        self.assertTrue(self.kn("ನೀಲಿ ಗೇಟ್", "लाल गेट", "hi-IN"))                                        # colour

    def test_cannot_find_is_a_negation_in_kannada(self):
        # the real rider line "I am on the main road, I can't find the address"
        src = "ನಾನು ಮುಖ್ಯರಸ್ತೆಯಲ್ಲಿದ್ದೀನಿ ಅಡ್ರೆಸ್ ಸಿಕ್ತಿಲ್ಲ"
        self.assertEqual(self.kn(src, "मैं मुख्य सड़क पर हूँ, पता नहीं मिल रहा।", "hi-IN"), [])
        self.assertTrue(self.kn(src, "मैं मुख्य सड़क पर हूँ, पता मिल गया।", "hi-IN"))              # the "not" was lost
        self.assertEqual(self.kn("ನಾನು ಇಲ್ಲಿ ನಿಂತಿದ್ದೀನಿ", "मैं यहाँ खड़ा हूँ", "hi-IN"), [])       # "ಇಲ್ಲಿ" (here) is not a negation

    def test_a_word_that_only_starts_like_a_number_is_not_a_number(self):
        # "ಹತ್ತಿರ" (near) starts like "ಹತ್ತು" (ten): it must not be read as ten
        self.assertEqual(self.kn("ನಾನು ಗೇಟ್ ಹತ್ತಿರ ನಿಂತಿದ್ದೀನಿ", "मैं गेट के पास खड़ा हूँ", "hi-IN"), [])

    def test_english_right_here_is_not_the_direction_right(self):
        self.assertEqual(guard.check("ನಾನು ಇಲ್ಲೇ ಇದ್ದೀನಿ", "I am right here.", "en", src="kn-IN"), [])
        self.assertEqual(guard.check("do gali baad right", "Turn right after two lanes.", "en"), [])

    def test_a_misheard_transcript_is_translated_faithfully_and_the_guard_cannot_help(self):
        # Prisma wrote this for "where are you bro, I'm here"; the model invented sentences, and only the invented "not" gives them away
        garbled = "ಎಲ್ಲದ ಬ್ರೋ ನಾನು ಇಲ್ಲದ"
        self.assertTrue(self.kn(garbled, "सब ठीक है, ब्रो! मैं नहीं हूँ.", "hi-IN"))
        self.assertEqual(self.kn(garbled, "सब ठीक है, ब्रो! मैं यहाँ हूँ।", "hi-IN"), [])           # an invented sentence with no "not" would pass


if __name__ == "__main__":
    unittest.main()
