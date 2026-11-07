"""The documents must match the data. Skipped when out/ has not been generated (for example on a fresh clone)."""
import csv
import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))

import build_docs  # noqa: E402
import evaluate_unseen  # noqa: E402
from heldout import HELDOUT_C  # noqa: E402
from verify import verify  # noqa: E402

OUT = ROOT / "out"
NEEDED = [OUT / p for p in ("results.json", "sweep_summary.json", "hard_summary.json", "hard_results.csv", "short_audio.json",
                            "determinism.json", "demo/results.json")]
HAVE_OUT = all(p.exists() for p in NEEDED)


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


class TestRequirementsAndTemplates(unittest.TestCase):
    def test_requirements_pins_the_one_dependency(self):
        lines = [l for l in read("requirements.txt").splitlines() if l and not l.startswith("#")]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("httpx"))

    def test_templates_use_only_known_placeholders(self):
        known = set(build_docs.facts().keys()) if HAVE_OUT else None
        for name in ("README.template.md", "SUBMISSION.template.md"):
            used = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", read(name)))
            if known is not None:
                self.assertEqual(used - known, set(), name)

    def test_templates_have_no_hand_typed_result_percentages(self):
        """Every percentage in a template must come from a placeholder, never from a person typing a number."""
        for name in ("README.template.md", "SUBMISSION.template.md"):
            text = re.sub(r"\{\{[A-Z0-9_]+\}\}", "", read(name))
            self.assertEqual(re.findall(r"\d+\s?%", text), [], name)


@unittest.skipUnless(HAVE_OUT, "out/ has not been generated")
class TestDocsMatchData(unittest.TestCase):
    def test_documents_are_up_to_date(self):
        rendered = build_docs.render_all()
        for name, text in rendered.items():
            self.assertEqual(read(name), text, f"{name} is stale: run python build_docs.py")

    def test_no_placeholders_or_secrets_leak_into_the_documents(self):
        key = None
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("GNANI_API_KEY="):
                    key = line.split("=", 1)[1].strip()
        for name in ("README.md", "SUBMISSION.md"):
            text = read(name)
            self.assertNotIn("{{", text)
            if key and len(key) > 12:
                self.assertNotIn(key, text, name)
            self.assertNotRegex(text, r"vach_[A-Za-z0-9]{20,}")

    # ---- independent recomputation of a few figures, straight from the raw files
    def test_replay_counts_recomputed_from_the_raw_sweep_rows(self):
        with open(OUT / "hard_results.csv", newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["part"] == "hard"]
        counts = {"ACCEPT": 0, "CONFIRM": 0, "ASK_AGAIN": 0, "MISMATCH": 0}
        for r in rows:
            counts[verify(r["ref"], r["hyp"]).decision] += 1
        line = f"{counts['ACCEPT']} accepted, {counts['CONFIRM']} read-back, {counts['ASK_AGAIN']} ask-again, {counts['MISMATCH']} mismatch of {len(rows)}"
        for name in ("README.md", "SUBMISSION.md"):
            self.assertIn(line, read(name))

    def test_first_sweep_row_recomputed_from_the_raw_rows(self):
        with open(OUT / "sweep_results.csv", newline="", encoding="utf-8") as f:
            clean = [r for r in csv.DictReader(f) if r["cond"] == "0dB"]
        exact = round(100 * sum(int(r["exact"]) for r in clean) / len(clean))
        self.assertIn(f"| 0dB | {exact}% |", read("README.md"))

    def test_extractor_recall_on_the_untuned_set(self):
        m = evaluate_unseen.measure(HELDOUT_C)
        cell = f"{m['found']}/{m['wanted']} ({m['recall']}%)"
        self.assertIn(f"| C | {m['phrases']} | {cell} | {m['false_values']} | not used for tuning |", read("README.md"))
        self.assertIn(cell, read("SUBMISSION.md"))

    def test_short_audio_acceptances_recomputed(self):
        data = json.loads((OUT / "short_audio.json").read_text(encoding="utf-8"))
        text = read("README.md")
        for u in data["utterances"]:
            n = sum(r["decision"] == "ACCEPT" for r in u["results"])
            self.assertIn(f"| {u['label']} | {u['seconds']} s | {n} of {len(u['results'])} |", text)

    def test_determinism_counts_recomputed(self):
        data = json.loads((OUT / "determinism.json").read_text(encoding="utf-8"))
        t = sum(x["distinct_outputs"] == data["repeats"] for x in data["timbre_identical_requests"])
        p = sum(x["distinct_transcripts"] == 1 for x in data["prisma_identical_audio"])
        self.assertIn(f"Timbre: {t} of {len(data['timbre_identical_requests'])} repeated requests", read("README.md"))
        self.assertIn(f"Prisma: {p} of {len(data['prisma_identical_audio'])} repeated audio files", read("README.md"))

    def test_demo_outcomes_match_the_results_file(self):
        demo = json.loads((OUT / "demo" / "results.json").read_text(encoding="utf-8"))
        text = read("README.md")
        for r in demo["ladder"]:
            self.assertIn(f"| {r['cond']} |", text)
            self.assertIn(f"{r['decision']} ({r['reason']})", text)
        for s in demo["steps"]:
            self.assertIn(f"| {s['step']} | {s['phrase']} | {s['kind']} {s['snr']} dB |", text)
        live = [a["action"] for e in demo["steps"] + [demo["stress"]] for a in e["attempts"]]
        if not {"CONFIRM_YN", "ASK_AGAIN", "FALLBACK_TAP"} & set(live):
            self.assertIn("No read-back, ask-again or tap fallback happened in this run's live scenes.", text)

    def test_call_results_recomputed_from_the_raw_results_file(self):
        call = json.loads((OUT / "call" / "results.json").read_text(encoding="utf-8"))
        label = {"translated": "translated", "partial": "partly translated", "untranslated": "not translated"}
        counts = ", ".join(f"{sum(t['status'] == k for t in call['turns'])} {v}" for k, v in label.items())
        for name in ("README.md", "SUBMISSION.md"):
            self.assertIn(f"{len(call['turns'])} turns between two synthetic voices: {counts}" if name == "README.md" else counts, read(name))
        for t in call["turns"]:
            self.assertIn(f"| {t['n']} |", read("README.md"))
            if t["output"]:
                self.assertIn(f"`{t['output']}`", read("README.md"))

    def test_roundtrip_table_recomputed(self):
        rows = json.loads((OUT / "render_roundtrip.json").read_text(encoding="utf-8"))
        for lang, name in (("hi-IN", "Hindi"), ("kn-IN", "Kannada")):
            r = [x for x in rows if x["lang"] == lang and x["phrase"]]
            self.assertIn(f"| {name} | {len(r)} | {sum(x['same_meaning'] for x in r)} of {len(r)} | {sum(x['exact_text'] for x in r)} of {len(r)} |", read("README.md"))

    def test_every_limit_in_the_readme_is_one_the_code_really_refuses(self):
        import translate as T
        text = read("README.md")
        for title, example, lang, reason in T.LIMITS:
            r = T.translate(example, lang, "kn-IN" if lang == "hi-IN" else "hi-IN")
            self.assertEqual(r.status, "untranslated", title)
            self.assertIn(f"| {title} | `{example}` | {r.reason_text} |", text)

    def test_the_kannada_caveat_is_in_both_documents(self):
        for name in ("README.md", "SUBMISSION.md"):
            self.assertIn("native-speaker review", read(name), name)

    def test_the_documents_name_what_is_simulated_and_what_is_untested(self):
        readme, sub = read("README.md"), read("SUBMISSION.md")
        for needle in ("synthetic", "simulated", "not been tried with real", "REPLAYED FROM THE SWEEP, NOT FROM THIS RUN"):
            self.assertIn(needle, readme, needle)
        for needle in ("synthetic", "No buyer has said they would pay", "#GnaniAI", "#GreatIndianAIInternshipChallenge", "[EDIT]"):
            self.assertIn(needle, sub, needle)


if __name__ == "__main__":
    unittest.main()
