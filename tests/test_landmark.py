import csv
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from checkpoint import Checkpoint, parse_yes_no  # noqa: E402
from extraction import CRITICAL, extract, split_chain  # noqa: E402
from heldout import HELDOUT  # noqa: E402
from sweep import PHRASES as ORIG  # noqa: E402
from sweep2 import HARD  # noqa: E402
from verify import ACCEPT, ASK_AGAIN, CONFIRM, MISMATCH, verify  # noqa: E402

# expected critical slots, written out by hand (not derived from the extractor)
EXPECTED = {
    "मंदिर के पीछे नीला गेट": dict(anchor="TEMPLE", relation="BEHIND", colour="BLUE"),
    "मंदिर के पीछे लाल गेट": dict(anchor="TEMPLE", relation="BEHIND", colour="RED"),
    "मंदिर के सामने नीला गेट": dict(anchor="TEMPLE", relation="FRONT", colour="BLUE"),
    "मस्जिद के पीछे नीला गेट": dict(anchor="MOSQUE", relation="BEHIND", colour="BLUE"),
    "पहली गली में हरा मकान": dict(ordinal="1", colour="GREEN"),
    "दूसरी गली में हरा मकान": dict(ordinal="2", colour="GREEN"),
    "दूसरी गली में पीला मकान": dict(ordinal="2", colour="YELLOW"),
    "तीसरी गली में पीला मकान": dict(ordinal="3", colour="YELLOW"),
    "दाएं तरफ पहली दुकान": dict(side="RIGHT", ordinal="1"),
    "बाएं तरफ पहली दुकान": dict(side="LEFT", ordinal="1"),
    "दाएं तरफ दूसरी दुकान": dict(side="RIGHT", ordinal="2"),
    "बाएं तरफ दूसरी दुकान": dict(side="LEFT", ordinal="2"),
    "देवळाच्या मागे निळे गेट": dict(anchor="TEMPLE", relation="BEHIND", colour="BLUE"),
    "देवळाच्या मागे लाल गेट": dict(anchor="TEMPLE", relation="BEHIND", colour="RED"),
    "देवळासमोर निळे गेट": dict(anchor="TEMPLE", relation="FRONT", colour="BLUE"),
    "मशिदीच्या मागे निळे गेट": dict(anchor="MOSQUE", relation="BEHIND", colour="BLUE"),
    "पहिल्या गल्लीतले हिरवे घर": dict(ordinal="1", colour="GREEN"),
    "दुसऱ्या गल्लीतले हिरवे घर": dict(ordinal="2", colour="GREEN"),
    "दुसऱ्या गल्लीतले पिवळे घर": dict(ordinal="2", colour="YELLOW"),
    "तिसऱ्या गल्लीतले पिवळे घर": dict(ordinal="3", colour="YELLOW"),
    "उजव्या बाजूला पहिले दुकान": dict(side="RIGHT", ordinal="1"),
    "डाव्या बाजूला पहिले दुकान": dict(side="LEFT", ordinal="1"),
    "उजव्या बाजूला दुसरे दुकान": dict(side="RIGHT", ordinal="2"),
    "डाव्या बाजूला दुसरे दुकान": dict(side="LEFT", ordinal="2"),
    # original phrasings
    "पेट्रोल पंप के सामने वाली गली": dict(anchor="PETROL_PUMP", relation="FRONT"),
    "स्कूल के बगल में लाल मकान": dict(anchor="SCHOOL", relation="NEAR", colour="RED"),
    "बड़े पीपल के पेड़ के नीचे": dict(anchor="TREE", relation="BELOW"),
    "दूसरी गली में हरे रंग का दरवाज़ा": dict(ordinal="2", colour="GREEN"),
    "पानी की टंकी के पास पीला घर": dict(anchor="TANK", relation="NEAR", colour="YELLOW"),
    "पोस्ट ऑफिस के ऊपर वाला फ्लैट": dict(anchor="POST_OFFICE", relation="ABOVE"),
    "पेट्रोल पंपासमोरची गल्ली": dict(anchor="PETROL_PUMP", relation="FRONT"),
    "शाळेच्या शेजारी लाल घर": dict(anchor="SCHOOL", relation="NEAR", colour="RED"),
    "मोठ्या वडाच्या झाडाखाली": dict(anchor="TREE", relation="BELOW"),
    "पाण्याच्या टाकीजवळ पिवळे घर": dict(anchor="TANK", relation="NEAR", colour="YELLOW"),
    "मारुती मंदिरानंतर तिसरे घर": dict(anchor={"HANUMAN", "TEMPLE"}, relation="AFTER", ordinal="3"),
    "हनुमान मंदिर के बाद तीसरा मकान": dict(anchor={"HANUMAN", "TEMPLE"}, relation="AFTER", ordinal="3"),
    "पोस्ट ऑफिसच्या वरचा फ्लॅट": dict(anchor="POST_OFFICE", relation="ABOVE"),
    "बस स्टँडपासून सरळ जाऊन उजवीकडे वळा": dict(anchor="BUS_STAND", relation={"FROM", "STRAIGHT"}, side="RIGHT"),
    "बस स्टैंड से सीधे जाकर दाएं मुड़िए": dict(anchor="BUS_STAND", relation={"FROM", "STRAIGHT"}, side="RIGHT"),
    "मस्जिद के सामने किराने की दुकान": dict(anchor="MOSQUE", relation="FRONT"),
    "मशिदीसमोर किराणा दुकान": dict(anchor="MOSQUE", relation="FRONT"),
    "मंदिर के पीछे नीला गेट ": dict(anchor="TEMPLE", relation="BEHIND", colour="BLUE"),
}


def as_set(v):
    return {v} if isinstance(v, str) else set(v)


def all_groups():
    """(label, [phrases]) for every sibling group, hard and original."""
    for lang, gs in HARD.items():
        for g, items in gs.items():
            yield g, [p for p, _, _ in items]
    for lang, items in ORIG.items():
        yield "orig-" + lang, [p for p, _, _ in items]


class TestExtraction(unittest.TestCase):
    def test_slots_for_every_listed_phrase(self):
        for phrase, want in EXPECTED.items():
            got = extract(phrase)
            for slot in CRITICAL:
                with self.subTest(phrase=phrase, slot=slot):
                    self.assertEqual(set(got[slot]), as_set(want[slot]) if slot in want else set())

    def test_all_phrases_have_at_least_one_critical_slot(self):
        for _, phrases in all_groups():
            for p in phrases:
                with self.subTest(phrase=p):
                    self.assertTrue(any(extract(p)[s] for s in CRITICAL))

    def test_split_chain_keeps_order(self):
        steps = split_chain("मंदिर के पीछे नीला गेट, फिर दूसरी गली में हरा मकान")
        self.assertEqual(len(steps), 2)
        self.assertEqual(set(steps[0]["colour"]), {"BLUE"})
        self.assertEqual(set(steps[1]["colour"]), {"GREEN"})
        self.assertEqual(set(steps[1]["ordinal"]), {"2"})


class TestVerify(unittest.TestCase):
    def test_exact_phrase_accepts_everywhere(self):
        for _, phrases in all_groups():
            for p in phrases:
                with self.subTest(phrase=p):
                    self.assertEqual(verify(p, p).decision, ACCEPT)

    def test_sibling_is_never_accepted(self):
        """Hearing a look-alike landmark must never pass for the expected one."""
        n = 0
        for g, phrases in all_groups():
            for i, exp in enumerate(phrases):
                for j, heard in enumerate(phrases):
                    if i == j:
                        continue
                    n += 1
                    with self.subTest(group=g, expected=exp, heard=heard):
                        self.assertNotEqual(verify(exp, heard).decision, ACCEPT)
        self.assertGreater(n, 100)

    def test_minimal_pairs_are_mismatches(self):
        """Within a hard group every sibling differs in a critical slot, so it must conflict."""
        for lang, gs in HARD.items():
            for g, items in gs.items():
                phrases = [p for p, _, _ in items]
                for i, exp in enumerate(phrases):
                    for j, heard in enumerate(phrases):
                        if i != j:
                            with self.subTest(group=g, expected=exp, heard=heard):
                                self.assertEqual(verify(exp, heard).decision, MISMATCH)

    def test_empty_and_short_ask_again(self):
        exp = "मंदिर के पीछे नीला गेट"
        for heard, reason in [("", "empty"), ("   ", "empty"), ("।", "empty"), ("हाँ", "too_short"), ("नीला", "too_short")]:
            with self.subTest(heard=heard):
                v = verify(exp, heard)
                self.assertEqual((v.decision, v.reason), (ASK_AGAIN, reason))

    def test_truncated_tail_asks_for_confirmation(self):
        v = verify("मंदिर के पीछे नीला गेट", "मंदिर के पीछे मिलना चाहिए")
        self.assertEqual(v.decision, CONFIRM)
        self.assertIn("colour", v.missing)

    def test_noise_garbage_asks_again(self):
        self.assertEqual(verify("मंदिर के पीछे नीला गेट", "ठीक है भाई कल मिलते हैं").decision, ASK_AGAIN)

    def test_wrong_colour_is_a_mismatch(self):
        v = verify("मंदिर के पीछे नीला गेट", "मंदिर के पीछे लाल गेट")
        self.assertEqual(v.decision, MISMATCH)
        self.assertEqual(v.conflicts[0][0], "colour")

    def test_marathi_suffix_variation_still_accepts(self):
        self.assertEqual(verify("पोस्ट ऑफिसच्या वरचा फ्लॅट", "पोस्ट ऑफिसचा वरचा फ्लॅट").decision, ACCEPT)

    def test_hindi_spelling_variants_accept(self):
        self.assertEqual(verify("दाएं तरफ दूसरी दुकान", "दाईं तरफ दूसरी दुकान").decision, ACCEPT)
        self.assertEqual(verify("दूसरी गली में हरे रंग का दरवाज़ा", "दूसरी गली में हरे रंग का दरवाजा").decision, ACCEPT)


class TestYesNo(unittest.TestCase):
    def test_parse(self):
        for text, want in [("हाँ", "yes"), ("हां जी", "yes"), ("हो", "yes"), ("बरोबर", "yes"),
                           ("नहीं", "no"), ("नाही", "no"), ("गलत", "no"),
                           ("हां नहीं", None), ("", None), ("पता नहीं चल रहा हां", None)]:
            with self.subTest(text=text):
                self.assertEqual(parse_yes_no(text), want)


class TestFlow(unittest.TestCase):
    EXP = "मंदिर के पीछे नीला गेट"

    def test_clean_accept(self):
        c = Checkpoint(self.EXP)
        self.assertEqual(c.hear(self.EXP).kind, "CONFIRMED")
        self.assertEqual((c.status, c.method), ("CONFIRMED", "voice"))

    def test_ask_again_then_accept(self):
        c = Checkpoint(self.EXP)
        self.assertEqual(c.hear("").kind, "ASK_AGAIN")
        self.assertEqual(c.hear(self.EXP).kind, "CONFIRMED")

    def test_truncated_then_yes(self):
        c = Checkpoint(self.EXP)
        a = c.hear("मंदिर के पीछे")
        self.assertEqual(a.kind, "CONFIRM_YN")
        self.assertIn(self.EXP, a.text)
        self.assertEqual(c.hear("हाँ").kind, "CONFIRMED")
        self.assertEqual(c.method, "yes")

    def test_truncated_then_no_is_not_found(self):
        c = Checkpoint(self.EXP)
        c.hear("मंदिर के पीछे")
        self.assertEqual(c.hear("नहीं").kind, "NOT_FOUND")
        self.assertEqual(c.status, "NOT_FOUND")

    def test_repeated_conflict_goes_to_yes_no(self):
        c = Checkpoint(self.EXP)
        self.assertEqual(c.hear("मंदिर के पीछे लाल गेट").kind, "ASK_AGAIN")
        a = c.hear("मंदिर के पीछे लाल गेट")
        self.assertEqual(a.kind, "CONFIRM_YN")
        self.assertTrue(a.reason.startswith("repeated_conflict"))

    def test_three_failures_fall_back_to_tap(self):
        c = Checkpoint(self.EXP)
        kinds = [c.hear("").kind, c.hear("").kind, c.hear("").kind]
        self.assertEqual(kinds, ["ASK_AGAIN", "ASK_AGAIN", "FALLBACK_TAP"])
        self.assertEqual(c.hear(self.EXP).kind, "FALLBACK_TAP")  # speech ignored while waiting for tap
        self.assertEqual(c.tap(True).kind, "CONFIRMED")
        self.assertEqual(c.method, "tap")

    def test_skip_leaves_unconfirmed_not_failed(self):
        c = Checkpoint(self.EXP)
        for _ in range(3):
            c.hear("")
        self.assertEqual(c.tap(None).kind, "UNCONFIRMED")

    def test_unclear_yes_no_eventually_falls_back(self):
        c = Checkpoint(self.EXP)
        c.hear("मंदिर के पीछे")
        self.assertEqual(c.hear("पता नहीं").kind, "CONFIRM_YN")
        self.assertEqual(c.hear("hmm").kind, "CONFIRM_YN")
        self.assertEqual(c.hear("शायद").kind, "FALLBACK_TAP")

    def test_marathi_prompts(self):
        c = Checkpoint("देवळाच्या मागे निळे गेट", "mr-IN")
        a = c.hear("देवळाच्या मागे")
        self.assertEqual(a.kind, "CONFIRM_YN")
        self.assertIn("बरोबर", a.text)
        self.assertEqual(c.hear("हो").kind, "CONFIRMED")

    def test_final_action_is_idempotent(self):
        c = Checkpoint(self.EXP)
        first = c.hear(self.EXP)
        self.assertIs(c.hear("कुछ और"), first)


class TestRealTranscripts(unittest.TestCase):
    """Replay the real Prisma outputs from the noise sweeps (skipped if the CSVs are absent)."""

    def rows(self):
        out = []
        for name in ("hard_results.csv", "sweep_results.csv"):
            path = os.path.join(ROOT, "out", name)
            if os.path.exists(path):
                with open(path, newline="", encoding="utf-8") as f:
                    out += list(csv.DictReader(f))
        return out

    def test_no_sibling_transcript_is_ever_accepted(self):
        rows = self.rows()
        if not rows:
            self.skipTest("no sweep results")
        groups = {p: ps for _, ps in all_groups() for p in ps}
        false_accepts, checked = [], 0
        for r in rows:
            for other in groups.get(r["ref"], []):
                if other == r["ref"]:
                    continue
                checked += 1
                if verify(other, r["hyp"]).decision == ACCEPT:
                    false_accepts.append((r["cond"], other, r["hyp"]))
        self.assertGreater(checked, 500)
        self.assertEqual(false_accepts, [])


class TestVerifierHardening(unittest.TestCase):
    """Found in review: a transcript containing the expected word AND a contradicting one was accepted."""
    EXP = "मंदिर के पीछे नीला गेट"

    def test_contradicting_word_is_never_accepted(self):
        for heard in ["मंदिर के पीछे नीला गेट नहीं लाल गेट", "मंदिर के पीछे लाल गेट नीला", "नीला नहीं लाल है मंदिर के पीछे"]:
            with self.subTest(heard=heard):
                v = verify(self.EXP, heard)
                self.assertEqual(v.decision, MISMATCH)
                self.assertTrue(v.reason.startswith("ambiguous:colour"), v.reason)

    def test_a_second_landmark_in_the_same_breath_is_ambiguous(self):
        v = verify(self.EXP, "मंदिर के पीछे मस्जिद के पीछे नीला गेट")
        self.assertEqual((v.decision, v.reason), (MISMATCH, "ambiguous:anchor"))

    def test_negation_turns_an_accept_into_a_read_back(self):
        for exp, heard in [(self.EXP, "मंदिर के पीछे नीला गेट नहीं है"), ("देवळाच्या मागे निळे गेट", "देवळाच्या मागे निळे गेट नाही")]:
            with self.subTest(heard=heard):
                v = verify(exp, heard)
                self.assertEqual((v.decision, v.reason), (CONFIRM, "negation"))

    def test_negation_does_not_hide_a_conflict(self):
        self.assertEqual(verify(self.EXP, "मंदिर के पीछे लाल गेट नहीं").decision, MISMATCH)

    def test_the_plain_phrase_is_still_accepted(self):
        self.assertEqual(verify(self.EXP, self.EXP).decision, ACCEPT)

    def test_latin_script_hinglish_matches_a_devanagari_expectation(self):
        self.assertEqual(verify(self.EXP, "temple ke peeche neela gate").decision, ACCEPT)
        self.assertEqual(verify(self.EXP, "temple ke peeche laal gate").decision, MISMATCH)
        self.assertEqual(verify("स्कूल के सामने लाल घर", "school ke saamne laal ghar").decision, ACCEPT)


class TestExtractionHardening(unittest.TestCase):
    """Found in review: words and names that merely start like a lexicon entry produced false slots."""

    def values(self, text, slot):
        return set(extract(text)[slot])

    def test_names_foods_and_everyday_words_are_not_landmarks(self):
        for text in ["हरीश की दुकान के पीछे", "नीलेश का घर", "पेड़ा दुकान के पास", "वडापाव सेंटर के पीछे", "झाडू की दुकान",
                     "पहलवान की गली", "सावित्री बाई की दुकान", "पोस्टर वाली दुकान", "लक्ष्मी दाई का घर", "चौकी के पास कॉलेज",
                     "लालू की दुकान के पीछे", "नीलम की गली के सामने"]:
            e = extract(text)
            with self.subTest(text=text):
                for slot in ("anchor", "colour", "ordinal", "side"):
                    self.assertEqual(set(e[slot]), set(), (slot, e[slot]))

    def test_place_name_containing_a_colour_is_not_a_colour(self):
        self.assertEqual(self.values("लाल बाग के पास पीला मकान", "colour"), {"YELLOW"})
        self.assertEqual(self.values("लालबाग चौक के सामने", "colour"), set())

    def test_common_spelling_variants(self):
        self.assertEqual(self.values("दायें तरफ पहली दुकान", "side"), {"RIGHT"})
        self.assertEqual(self.values("बायें तरफ पहली दुकान", "side"), {"LEFT"})

    def test_more_colours(self):
        for text, want in [("सफेद गेट", "WHITE"), ("पांढरे घर", "WHITE"), ("काला गेट", "BLACK"), ("काळे गेट", "BLACK"), ("गुलाबी मकान", "PINK")]:
            with self.subTest(text=text):
                self.assertEqual(self.values(text, "colour"), {want})
        self.assertEqual(self.values("कालेज के पास", "colour"), set())     # 'college' is not black

    def test_added_anchors(self):
        for text, anchor in [("बँकेच्या वर पांढरे घर", "BANK"), ("पुलाखाली हिरवे गेट", "BRIDGE"), ("चौक के पास हरा मकान", "CHOWK"),
                             ("टपरीजवळ निळे दुकान", "TEA_STALL"), ("मंडई के पीछे", "MARKET"), ("अस्पताल के सामने", "HOSPITAL")]:
            with self.subTest(text=text):
                self.assertIn(anchor, self.values(text, "anchor"))
        self.assertNotIn("BRIDGE", self.values("पुलिस थाने के पास", "anchor"))

    def test_marathi_fused_relation(self):
        self.assertEqual(self.values("वडाच्या झाडामागे निळे घर", "relation"), {"BEHIND"})
        self.assertEqual(self.values("पाण्याच्या टाकीमागे पहिले दुकान", "relation"), {"BEHIND"})

    def test_roman_script_hinglish(self):
        e = extract("temple ke peeche neela gate")
        self.assertEqual((set(e["anchor"]), set(e["relation"]), set(e["colour"])), ({"TEMPLE"}, {"BEHIND"}, {"BLUE"}))
        e = extract("right side pe pehla ghar")
        self.assertEqual((set(e["side"]), set(e["ordinal"])), ({"RIGHT"}, {"1"}))
        self.assertEqual(set(extract("credit card")["colour"]), set())          # whole tokens only

    def test_heldout_phrases_regression(self):
        """In-sample now (the lexicon was extended after seeing these), so this guards regressions only."""
        want = ok = fp = 0
        for phrase, labels in HELDOUT:
            got = {k: set(v) for k, v in extract(phrase).items() if k in CRITICAL and v}
            want += sum(len(v) for v in labels.values())
            ok += sum(len(labels[k] & got.get(k, set())) for k in labels)
            fp += sum(len(got[k] - labels.get(k, set())) for k in got)
        self.assertGreaterEqual(ok / want, 0.9)
        self.assertEqual(fp, 0)


if __name__ == "__main__":
    unittest.main()
