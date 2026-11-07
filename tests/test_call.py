import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build_call_page  # noqa: E402
import build_page  # noqa: E402
import build_review_sheet  # noqa: E402
import call_demo  # noqa: E402
import translate as T  # noqa: E402
from test_demo import FakeApi  # noqa: E402


def run(api=None):
    d = Path(tempfile.mkdtemp())
    return call_demo.run(api or FakeApi("clean"), d), d


def embedded(html):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class TestCall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.dir = run()

    def test_each_scripted_turn_behaves_as_designed(self):
        self.assertEqual([t["status"] for t in self.res["turns"]], ["translated"] * 4 + ["partial", "untranslated"])

    def test_the_conversation_from_the_brief(self):
        outs = [t["output"] for t in self.res["turns"][:4]]
        self.assertEqual(outs, ["ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್", "दाएं तरफ दूसरा गेट", "ಹೌದು, ಸರಿ", "मिल गया"])
        self.assertEqual([t["who"] for t in self.res["turns"]], ["customer", "biker", "customer", "biker", "customer", "customer"])

    def test_the_customer_speaks_hindi_and_the_biker_kannada(self):
        for t in self.res["turns"]:
            self.assertEqual((t["src"], t["dst"]), ("hi-IN", "kn-IN") if t["who"] == "customer" else ("kn-IN", "hi-IN"))

    def test_translation_is_spoken_to_the_listener_in_their_language(self):
        t1 = self.res["turns"][0]
        self.assertEqual([(s["to"], s["lang"], s["voice"], s["kind"]) for s in t1["spoken"]], [("biker", "kn-IN", "Saanvi", "translation")])
        t2 = self.res["turns"][1]
        self.assertEqual([(s["to"], s["lang"], s["voice"]) for s in t2["spoken"]], [("customer", "hi-IN", "Nalini")])

    def test_partial_translation_also_tells_the_listener_something_was_left_out(self):
        t5 = self.res["turns"][4]
        self.assertEqual([s["kind"] for s in t5["spoken"]], ["translation", "notice"])
        self.assertEqual(t5["spoken"][1]["text"], T.NOTICE["kn-IN"]["partial"])
        self.assertIn("पांच", t5["not_understood"])

    def test_a_refusal_is_spoken_to_both_people_in_their_own_languages(self):
        t6 = self.res["turns"][5]
        self.assertEqual([(s["to"], s["lang"], s["text"]) for s in t6["spoken"]],
                         [("customer", "hi-IN", T.NOTICE["hi-IN"]["speaker"]), ("biker", "kn-IN", T.NOTICE["kn-IN"]["listener"])])
        self.assertEqual(t6["output"], "")

    def test_every_audio_file_exists_and_the_sequence_is_written(self):
        names = [t["said_audio"] for t in self.res["turns"]] + [s["audio"] for t in self.res["turns"] for s in t["spoken"]]
        for n in names:
            self.assertTrue((self.dir / n).exists(), n)
        with wave.open(str(self.dir / "call_sequence.wav")) as w:
            self.assertGreater(w.getnframes() / w.getframerate(), 8)
        self.assertEqual(json.loads((self.dir / "results.json").read_text(encoding="utf-8"))["turns"][0]["output"], "ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್")

    def test_a_misheard_turn_is_refused_never_guessed(self):
        class Deaf(FakeApi):
            def stt(self, audio, lang, hint=None, ctx=None):
                return "" if (ctx or {}).get("turn") == 2 else super().stt(audio, lang, hint, ctx)
        res, _ = run(Deaf("clean"))
        t2 = res["turns"][1]
        self.assertEqual((t2["status"], t2["output"], t2["reason"]), ("untranslated", "", "no_known_words"))
        self.assertEqual(t2["spoken"][0]["lang"], "kn-IN")                # the biker is told, in Kannada, to say it again

    def test_a_wrong_but_plausible_transcript_changes_the_meaning_it_does_not_hide_it(self):
        class Wrong(FakeApi):
            def stt(self, audio, lang, hint=None, ctx=None):
                return "भैया ये गेट दूसरा गेट बाएं तरफ वाला" if (ctx or {}).get("turn") == 1 else super().stt(audio, lang, hint, ctx)
        res, _ = run(Wrong("clean"))
        self.assertEqual(res["turns"][0]["output"], "ಎಡಗಡೆಯ ಎರಡನೇ ಗೇಟ್")      # a misheard side is translated faithfully, so the read-back must catch it
        self.assertEqual(res["turns"][0]["heard"], "भैया ये गेट दूसरा गेट बाएं तरफ वाला")


class TestCallPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.dir = run()
        cls.path, cls.missing = build_call_page.build(cls.dir)
        cls.html = cls.path.read_text(encoding="utf-8")
        cls.data = embedded(cls.html)

    def test_page_data_is_exactly_the_results(self):
        self.assertEqual(self.data["res"], self.res)
        self.assertEqual(self.missing, [])
        self.assertEqual(set(self.data["peaks"]), build_page.wav_files(self.res))

    def test_page_is_self_contained_and_safe(self):
        self.assertEqual(self.html.count("</script>"), 2)
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("__DATA__", self.html)

    def test_hostile_text_cannot_break_out(self):
        class Hostile(FakeApi):
            def stt(self, audio, lang, hint=None, ctx=None):
                t = super().stt(audio, lang, hint, ctx)
                return t + " </script><img src=x onerror=alert(1)>" if (ctx or {}).get("turn") == 1 else t
        res, d = run(Hostile("clean"))
        path, _ = build_call_page.build(d)
        html = path.read_text(encoding="utf-8")
        self.assertEqual(html.count("</script>"), 2)
        self.assertNotIn("</script><img", html)

    def test_what_it_can_and_cannot_do_is_computed_from_the_translator(self):
        cap = self.data["cap"]
        self.assertTrue(all(e["status"] == "translated" and e["output"] for e in cap["examples"]))
        self.assertEqual(len(cap["limits"]), len(T.LIMITS))
        self.assertTrue(all(l["status"] == "untranslated" and l["reason"] for l in cap["limits"]))
        self.assertEqual(cap["counts"], T.vocabulary_counts())

    def test_javascript_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = re.findall(r"<script>(.*?)</script>", self.html, re.S)[0]
        f = Path(tempfile.mkdtemp()) / "page.js"
        f.write_text(script, encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestReviewSheet(unittest.TestCase):
    def test_every_kannada_string_is_on_the_sheet_and_the_file_is_current(self):
        sheet = build_review_sheet.build()
        tables = [T.KN_ANCHOR, T.KN_REL_ADV, T.KN_REL_ADJ, T.KN_COLOUR, T.KN_ORD, T.KN_SIDE_ADV, T.KN_SIDE_ADJ, T.KN_TARGET, T.INTENT_TEXT["kn-IN"]]
        for table in tables:
            for value in table.values():
                self.assertIn(value, sheet)
        for n in T.NOTICE["kn-IN"].values():
            self.assertIn(n, sheet)
        self.assertIn("without a native-speaker review", sheet)
        path = Path(ROOT) / "kannada_review.md"
        if path.exists():
            self.assertEqual(path.read_text(encoding="utf-8"), sheet, "stale: run python build_review_sheet.py")


if __name__ == "__main__":
    unittest.main()
