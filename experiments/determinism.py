"""Is the pipeline repeatable? Live API calls (about 21), results saved to out/determinism.json.

Timbre: the same text and voice requested three times. Prisma: the same audio file sent three times.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gnani  # noqa: E402
import noise  # noqa: E402

OUT = gnani.HERE / "out"
REQUESTS = [("मला निळे गेट दिसले", "Ishaan", "mr-IN"), ("निळे गेट", "Ishaan", "mr-IN"), ("मंदिर के पीछे नीला गेट", "Nalini", "hi-IN")]
REPEATS = 3


def main():
    ok, why = gnani.check_network()
    if not ok:
        sys.exit(f"No network: {why}")
    out = {"repeats": REPEATS, "timbre_identical_requests": [], "prisma_identical_audio": []}
    for text, voice, lang in REQUESTS:
        hashes = [hashlib.sha1(gnani.tts(text, voice, lang)).hexdigest()[:10] for _ in range(REPEATS)]
        out["timbre_identical_requests"].append({"text": text, "voice": voice, "distinct_outputs": len(set(hashes))})
    wav = gnani.tts("मला निळे गेट दिसले", "Ishaan", "mr-IN")
    clips = [noise.to_8k((OUT / f"sweep_mr-IN_{i}.wav").read_bytes()) for i in range(1, 6)]
    for label, audio in [("clean", wav), ("bike 0 dB", noise.add_noise(wav, "bike", 0, clips, seed=14)),
                         ("babble 5 dB", noise.add_noise(wav, "babble", 5, clips, seed=15))]:
        heard = [gnani.stt(audio, "mr-IN") for _ in range(REPEATS)]
        out["prisma_identical_audio"].append({"audio": label, "distinct_transcripts": len(set(heard)), "transcripts": sorted(set(heard))})
    (OUT / "determinism.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
