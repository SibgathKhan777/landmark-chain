import itertools
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from extraction import CRITICAL, extract  # noqa: E402
from phrases import ANCHOR_HI, COLOUR, REL_HI, render  # noqa: E402

LANGS = ("hi-IN", "mr-IN")


def critical(slots):
    return {k: set(slots[k]) for k in CRITICAL if slots[k]}


class TestRender(unittest.TestCase):
    def check(self, slots, lang):
        phrase = render(slots, lang)
        self.assertIsNotNone(phrase, (slots, lang))
        got = extract(phrase)
        want = {k: set(v) for k, v in slots.items() if v}
        for k in CRITICAL:
            self.assertEqual(set(got[k]), want.get(k, set()), (phrase, k))
        self.assertEqual(set(got["target"]), want.get("target", set()), phrase)

    def test_round_trip_anchor_relation_colour_target(self):
        for lang in LANGS:
            for a, r, c, t in itertools.product(ANCHOR_HI, REL_HI, ("BLUE", "RED", "GREEN", "YELLOW"), ("GATE", "HOUSE")):
                with self.subTest(lang=lang, a=a, r=r, c=c, t=t):
                    self.check({"anchor": {a}, "relation": {r}, "colour": {c}, "target": {t}}, lang)

    def test_round_trip_side_ordinal_shop(self):
        for lang in LANGS:
            for side, o in itertools.product(("LEFT", "RIGHT"), ("1", "2", "3")):
                with self.subTest(lang=lang, side=side, o=o):
                    self.check({"side": {side}, "ordinal": {o}, "target": {"SHOP"}}, lang)

    def test_round_trip_lane_and_house(self):
        for lang in LANGS:
            for o, c in itertools.product(("1", "2", "3"), ("GREEN", "YELLOW")):
                with self.subTest(lang=lang, o=o, c=c):
                    self.check({"ordinal": {o}, "colour": {c}, "target": {"LANE", "HOUSE"}}, lang)

    def test_known_phrases(self):
        self.assertEqual(render(extract("मंदिर के पीछे नीला गेट"), "mr-IN"), "देवळाच्या मागे निळे गेट")
        self.assertEqual(render(extract("देवळासमोर निळे गेट"), "hi-IN"), "मंदिर के सामने नीला गेट")
        self.assertEqual(render(extract("दूसरी गली में हरा मकान"), "mr-IN"), "दुसऱ्या गल्लीतले हिरवे घर")
        self.assertEqual(render(extract("बाएं तरफ पहली दुकान"), "mr-IN"), "डाव्या बाजूला पहिले दुकान")

    def test_accepts_lists_from_route_steps(self):
        self.assertEqual(render({"colour": ["GREEN"], "target": ["HOUSE"]}, "hi-IN"), "हरा मकान")

    def test_unsupported_returns_none(self):
        self.assertIsNone(render({"anchor": {"TREE"}, "relation": {"BELOW"}}, "hi-IN"))
        self.assertIsNone(render({"colour": {"BLUE", "RED"}, "target": {"GATE"}}, "hi-IN"))
        self.assertIsNone(render({}, "hi-IN"))
        self.assertIsNone(render({"colour": {"BLUE"}, "target": {"GATE"}}, "ta-IN"))


if __name__ == "__main__":
    unittest.main()
