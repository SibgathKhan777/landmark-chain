"""How short can the rider's utterance be? Live API calls (about 40), results saved to out/short_audio.json.

Finding being tested: ~1 s utterances (two words, or one-word yes/no replies) came back glued or empty from Prisma,
while a full sentence did not. Same Timbre voice, same simulated noise, fixed seeds, one run, nothing re-rolled.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gnani  # noqa: E402
import noise  # noqa: E402
from checkpoint import parse_yes_no  # noqa: E402
from verify import verify  # noqa: E402

OUT = gnani.HERE / "out"
LANG, VOICE = "mr-IN", "Ishaan"
PHRASES = [("two words", "निळे गेट", "निळे गेट"),
           ("carrier sentence", "मला निळे गेट दिसले", "निळे गेट"),
           ("three-word landmark", "देवळाच्या मागे निळे गेट", "देवळाच्या मागे निळे गेट")]
CONDS = [("clean", None, None), ("bike 10 dB", "bike", 10), ("bike 5 dB", "bike", 5), ("bike 0 dB", "bike", 0)]
YESNO = [("Zahira", "हो", "yes"), ("Zahira", "नाही", "no"), ("Ishaan", "हो", "yes"), ("Ishaan", "नाही", "no"),
         ("Zahira", "हो, बरोबर आहे", "yes"), ("Zahira", "नाही, चुकीचे आहे", "no")]


def main():
    ok, why = gnani.check_network()
    if not ok:
        sys.exit(f"No network: {why}")
    clips = [noise.to_8k((OUT / f"sweep_mr-IN_{i}.wav").read_bytes()) for i in range(1, 6)]   # babble sources
    res = {"lang": LANG, "voice": VOICE, "utterances": [], "yes_no": []}
    for label, said, expected in PHRASES:
        wav = gnani.tts(said, VOICE, LANG)
        s, sr = gnani.read_wav(wav)
        row = {"label": label, "said": said, "expected": expected, "seconds": round(len(s) / sr, 2), "results": []}
        for i, (cn, kind, snr) in enumerate(CONDS):
            audio = wav if kind is None else noise.add_noise(wav, kind, snr, clips, seed=11 + i)
            heard = gnani.stt(audio, LANG)
            v = verify(expected, heard)
            row["results"].append({"cond": cn, "heard": heard, "decision": v.decision, "reason": v.reason})
        res["utterances"].append(row)
    for voice, said, want in YESNO:
        wav = gnani.tts(said, voice, LANG)
        s, sr = gnani.read_wav(wav)
        out = {"voice": voice, "said": said, "want": want, "seconds": round(len(s) / sr, 2)}
        for name, audio in (("raw", wav), ("padded", gnani.pad_silence(wav))):
            heard = gnani.stt(audio, LANG)
            out[name] = {"heard": heard, "parsed": parse_yes_no(heard)}
        res["yes_no"].append(out)
    (OUT / "short_audio.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in res["utterances"]:
        print(f"\n{row['label']}: {row['said']!r} ({row['seconds']} s)")
        for r in row["results"]:
            print(f"  {r['cond']:<11} {r['heard']!r:<34} {r['decision']}")
    print("\nyes/no replies (parsed yes/no, want in brackets):")
    for y in res["yes_no"]:
        print(f"  {y['voice']:<7} {y['said']!r:<22} {y['seconds']} s  raw -> {y['raw']['parsed']}   padded -> {y['padded']['parsed']}   [{y['want']}]")


if __name__ == "__main__":
    main()
