"""Can Timbre say what the translator writes, and does Prisma recognise it again? Live API calls (about 56),
results saved to out/render_roundtrip.json.

For each landmark meaning below, the translator writes it in Hindi and in Kannada, Timbre speaks it (clean, no noise), Prisma
transcribes it in the same language, and the extractor reads the transcript. A match means the meaning survived speech and
recognition. It does NOT show that the wording is natural: that needs a native speaker (see kannada_review.md).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gnani  # noqa: E402
from extraction import CRITICAL, extract  # noqa: E402
from translate import render  # noqa: E402

OUT = gnani.HERE / "out"
VOICES = {"hi-IN": ["Nalini", "Deepak"], "kn-IN": ["Kavin", "Saanvi"]}
MEANINGS = [
    {"side": ["RIGHT"], "ordinal": ["2"], "target": ["GATE"]},
    {"anchor": ["TEMPLE"], "relation": ["BEHIND"], "colour": ["BLUE"], "target": ["GATE"]},
    {"anchor": ["TANK"], "relation": ["NEAR"], "colour": ["YELLOW"], "target": ["HOUSE"]},
    {"ordinal": ["3"], "colour": ["GREEN"], "target": ["LANE", "HOUSE"]},
    {"side": ["LEFT"], "ordinal": ["1"], "target": ["SHOP"]},
    {"anchor": ["SCHOOL"], "relation": ["FRONT"]},
    {"anchor": ["TREE"], "relation": ["BELOW"]},
    {"anchor": ["BANK"], "relation": ["ABOVE"], "colour": ["WHITE"], "target": ["HOUSE"]},
    {"anchor": ["MOSQUE"], "relation": ["AFTER"], "colour": ["RED"], "target": ["GATE"]},
    {"anchor": ["CHOWK"], "relation": ["NEAR"]},
    {"anchor": ["HOSPITAL"], "relation": ["BEHIND"], "colour": ["BLACK"], "target": ["DOOR"]},
    {"anchor": ["BRIDGE"], "relation": ["BELOW"]},
    {"anchor": ["HANUMAN", "TEMPLE"], "relation": ["FRONT"], "colour": ["GREEN"], "target": ["GATE"]},
    {"anchor": ["PETROL_PUMP"], "relation": ["NEAR"], "colour": ["PINK"], "target": ["SHOP"]},
]


def main():
    ok, why = gnani.check_network()
    if not ok:
        sys.exit(f"No network: {why}")
    rows = []
    for lang in ("hi-IN", "kn-IN"):
        for i, meaning in enumerate(MEANINGS):
            phrase = render(meaning, lang)
            if phrase is None:
                rows.append({"lang": lang, "meaning": meaning, "phrase": None})
                continue
            voice = VOICES[lang][i % 2]
            heard = gnani.stt(gnani.tts(phrase, voice, lang), lang)
            want = {k: set(meaning.get(k, [])) for k in CRITICAL}
            got = {k: set(v) for k, v in extract(heard).items() if k in CRITICAL}
            got = {k: got.get(k, set()) for k in CRITICAL}
            rows.append({"lang": lang, "voice": voice, "meaning": meaning, "phrase": phrase, "heard": heard,
                         "exact_text": heard.strip(" ।,.") == phrase.strip(),
                         "same_meaning": want == got})
    (OUT / "render_roundtrip.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for lang in ("hi-IN", "kn-IN"):
        r = [x for x in rows if x["lang"] == lang and x["phrase"]]
        print(f"\n{lang}: same meaning {sum(x['same_meaning'] for x in r)} of {len(r)}, identical text {sum(x['exact_text'] for x in r)} of {len(r)}")
        for x in r:
            if not x["same_meaning"] or not x["exact_text"]:
                print(f"   {'MEANING LOST' if not x['same_meaning'] else 'wording differs'}: {x['phrase']!r} -> {x['heard']!r}")


if __name__ == "__main__":
    main()
