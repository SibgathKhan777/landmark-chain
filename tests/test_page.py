import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build_page  # noqa: E402
import demo  # noqa: E402
import gnani  # noqa: E402
from test_demo import FakeApi  # noqa: E402

CSV_HEADER = ["part", "lang", "group", "idx", "cond", "ref", "hyp"]
CSV_ROWS = [
    ["hard", "mr-IN", "M-A", "0", "babble@5", "देवळाच्या मागे निळे गेट", "देवळाच्या मागे"],
    ["hard", "hi-IN", "H-B", "2", "babble@5", "दूसरी गली में पीला मकान", ""],
]


def make_sweep_csv():
    import csv
    path = Path(tempfile.mkdtemp()) / "hard_results.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        w.writerows(CSV_ROWS)
    return path


def run_demo(api=None, stress=True, replay=True):
    d = tempfile.mkdtemp()
    demo.run(api or FakeApi("stress"), d, "mr-IN", clock=lambda: 1_800_000_000.0, stress=stress, replay=replay,
             sweep_csv=make_sweep_csv())
    return Path(d)


def embedded(html):
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class TestPeaks(unittest.TestCase):
    def test_waveform_follows_the_audio(self):
        quiet_then_loud = [0] * 4800 + [12000, -12000] * 2400
        path = Path(tempfile.mkdtemp()) / "x.wav"
        path.write_bytes(gnani.write_wav(quiet_then_loud, 16000))
        p = build_page.peaks(path)
        self.assertEqual(len(p), build_page.BUCKETS)
        self.assertEqual(max(p), 1.0)
        self.assertTrue(all(x == 0 for x in p[:40]))
        self.assertTrue(all(x == 1.0 for x in p[-40:]))

    def test_silent_clip_does_not_divide_by_zero(self):
        path = Path(tempfile.mkdtemp()) / "s.wav"
        path.write_bytes(gnani.write_wav([0] * 8000, 16000))
        self.assertTrue(all(x == 0 for x in build_page.peaks(path)))


class TestPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_demo()
        cls.path, cls.missing = build_page.build(cls.out)
        cls.html = cls.path.read_text(encoding="utf-8")
        cls.data = embedded(cls.html)
        cls.results = json.loads((cls.out / "results.json").read_text(encoding="utf-8"))

    def test_page_is_written_and_nothing_is_left_to_fill_in(self):
        self.assertTrue(self.path.exists())
        self.assertNotIn("__DATA__", self.html)
        self.assertEqual(self.missing, [])

    def test_embedded_results_are_exactly_the_real_results(self):
        self.assertEqual(self.data["res"], self.results)

    def test_every_referenced_clip_exists_and_has_a_waveform(self):
        files = build_page.wav_files(self.results)
        self.assertGreater(len(files), 15)
        self.assertEqual(set(self.data["peaks"]), files)
        for f in files:
            self.assertTrue((self.out / f).exists(), f)
            p = self.data["peaks"][f]
            self.assertEqual(len(p), build_page.BUCKETS)
            self.assertTrue(all(0 <= x <= 1 for x in p))
        self.assertTrue(all(d > 0 for d in self.data["dur"].values()))

    def test_every_scene_carries_its_audio(self):
        r = self.results
        self.assertTrue(all(c["audio"] for c in r["customers"]))
        self.assertTrue(all(s["next_audio"] and a["audio"] for s in r["steps"] for a in s["attempts"]))
        self.assertTrue(all(x["audio"] for x in r["ladder"]))
        self.assertTrue(all(a["audio"] for a in r["stress"]["attempts"]))

    def test_replay_is_labelled_on_the_page(self):
        self.assertIn("REPLAYED FROM THE SWEEP, NOT FROM THIS RUN", self.html)
        self.assertIn("scripted reply, not recorded", self.html)
        self.assertIn("Synthetic voices and simulated noise", self.html)

    def test_page_makes_no_network_requests(self):
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)

    def test_only_the_two_expected_script_blocks(self):
        self.assertEqual(self.html.count("</script>"), 2)

    def test_javascript_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        scripts = re.findall(r"<script>(.*?)</script>", self.html, re.S)
        self.assertEqual(len(scripts), 1)
        f = Path(tempfile.mkdtemp()) / "page.js"
        f.write_text(scripts[0], encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestPageSafety(unittest.TestCase):
    def test_hostile_transcript_text_cannot_break_out_of_the_data_block(self):
        class Hostile(FakeApi):
            def stt(self, audio, lang, hint=None, ctx=None):
                text = super().stt(audio, lang, hint, ctx)
                return text + " </script><img src=x onerror=alert(1)>" if (ctx or {}).get("snr") == 20 else text
        out = run_demo(Hostile("clean"), stress=False, replay=False)
        path, _ = build_page.build(out)
        html = path.read_text(encoding="utf-8")
        self.assertEqual(html.count("</script>"), 2)
        self.assertNotIn("</script><img", html)
        heard = embedded(html)["res"]["customers"][0]["heard"]
        self.assertIn("</script><img src=x onerror=alert(1)>", heard)        # preserved as text, not markup
        self.assertIn("textContent", html)                                    # rendered through text nodes

    def test_page_builds_without_the_optional_scenes(self):
        out = run_demo(FakeApi("clean"), stress=False, replay=False)
        path, missing = build_page.build(out)
        data = embedded(path.read_text(encoding="utf-8"))
        self.assertNotIn("stress", data["res"])
        self.assertNotIn("replay", data["res"])
        self.assertEqual(missing, [])

    def test_missing_audio_is_reported_not_hidden(self):
        out = run_demo(FakeApi("clean"), stress=False, replay=False)
        victim = sorted(out.glob("3_ladder_*.wav"))[0]
        victim.unlink()
        path, missing = build_page.build(out)
        self.assertEqual(missing, [victim.name])
        self.assertEqual(embedded(path.read_text(encoding="utf-8"))["missing"], [victim.name])

    def test_a_run_with_no_route_refuses_to_build(self):
        class Silent(FakeApi):
            def stt(self, *a, **k):
                return ""
        d = tempfile.mkdtemp()
        demo.run(Silent(), d, "mr-IN", clock=lambda: 1_800_000_000.0)
        with self.assertRaises(SystemExit):
            build_page.build(d)


if __name__ == "__main__":
    unittest.main()
