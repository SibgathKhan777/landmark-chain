import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "experiments"))

import hinglish_edge_cases as H  # noqa: E402
from translate import translate  # noqa: E402


class TestHinglishEdgeCases(unittest.TestCase):
    def test_every_case_behaves_as_written_down(self):
        bad = [(r["text"], r["expected"], r["got"]) for r in H.run() if not r["ok"]]
        self.assertEqual(bad, [], "cases that no longer behave as expected")

    def test_the_set_covers_every_kind_of_trap(self):
        groups = {c[0] for c in H.CASES}
        for g in ("negation", "questions", "conditions", "someone else", "multi-step routes", "distances and counts",
                  "real Prisma, Hindi mode", "real Prisma, English mode"):
            self.assertIn(g, groups)

    def test_a_partial_translation_never_leaves_out_a_word_that_changes_the_meaning(self):
        """Whenever only part of a sentence is spoken, the words left out must not be conditions, other people, distances or negations."""
        changes_meaning = {"agar", "jab", "tab", "wo", "driver", "dost", "meter", "signal", "gali", "nahi", "mat", "tak", "kya"}
        partial = [t for _, t, (kind, _) in H.CASES if kind == "partial"]
        self.assertGreaterEqual(len(partial), 4)
        for text in partial:
            r = translate(text, "hi-IN", "en")
            self.assertEqual(r.status, "partial", text)
            self.assertFalse(changes_meaning & set(r.untranslated), text)

    def test_both_directions_of_a_two_turn_route_come_out_in_order(self):
        self.assertEqual(translate("बाएं मुड़ो फिर दाएं मुड़ो", "hi-IN", "en").output, "turn left, turn right")
        self.assertEqual(translate("दाएं मुड़ो फिर बाएं मुड़ो", "hi-IN", "kn-IN").output, "ಬಲಕ್ಕೆ ತಿರುಗಿ, ಎಡಕ್ಕೆ ತಿರುಗಿ")

    def test_a_side_with_no_landmark_is_never_written_as_one(self):
        for text in ("right left hojao", "राइट ले लो लेफ्ट"):
            r = translate(text, "hi-IN", "en")
            self.assertEqual(r.status, "untranslated", text)
            self.assertNotIn("on the", r.english)

    def test_the_right_hand_idiom_is_not_read_as_straight(self):
        r = translate("सीधे हाथ पर मुड़ो", "hi-IN", "en")
        self.assertEqual(r.output, "turn right")
        self.assertEqual(translate("उल्टे हाथ पर मुड़ो", "hi-IN", "en").output, "turn left")

    def test_the_landmark_path_still_works_next_to_a_turn(self):
        r = translate("right le lo phir second gate left wala", "hi-IN", "en")
        self.assertIn("turn right", r.output)


if __name__ == "__main__":
    unittest.main()
