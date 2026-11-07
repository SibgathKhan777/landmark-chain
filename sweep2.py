"""Harder sweep: minimal-pair landmark phrasings + bike-like noise (engine hum, babble).

Part A: 24 phrasings in groups of 4 that differ by one detail (colour, landmark, lane, side).
        Identification is scored within the group (the hard case).
Part B: the original 20 phrasings re-run under bike noise.
All audio is synthetic (Timbre). Noise is synthetic too.
"""
import csv
import difflib
import json
import sys
import time
import zlib
from collections import defaultdict

import gnani
import noise
from sweep import PHRASES as ORIG, norm, wer

OUT = gnani.HERE / "out"

# group -> list of (phrase, distinguishing words, voice)
HARD = {
    "hi-IN": {
        "H-A": [("मंदिर के पीछे नीला गेट", ["मंदिर", "पीछे", "नीला"], "Nalini"),
                ("मंदिर के पीछे लाल गेट", ["मंदिर", "पीछे", "लाल"], "Deepak"),
                ("मंदिर के सामने नीला गेट", ["मंदिर", "सामने", "नीला"], "Nalini"),
                ("मस्जिद के पीछे नीला गेट", ["मस्जिद", "पीछे", "नीला"], "Deepak")],
        "H-B": [("पहली गली में हरा मकान", ["पहली", "हरा"], "Nalini"),
                ("दूसरी गली में हरा मकान", ["दूसरी", "हरा"], "Deepak"),
                ("दूसरी गली में पीला मकान", ["दूसरी", "पीला"], "Nalini"),
                ("तीसरी गली में पीला मकान", ["तीसरी", "पीला"], "Deepak")],
        "H-C": [("दाएं तरफ पहली दुकान", ["दाएं", "पहली"], "Nalini"),
                ("बाएं तरफ पहली दुकान", ["बाएं", "पहली"], "Deepak"),
                ("दाएं तरफ दूसरी दुकान", ["दाएं", "दूसरी"], "Nalini"),
                ("बाएं तरफ दूसरी दुकान", ["बाएं", "दूसरी"], "Deepak")],
    },
    "mr-IN": {
        "M-A": [("देवळाच्या मागे निळे गेट", ["देवळाच्या", "मागे", "निळे"], "Zahira"),
                ("देवळाच्या मागे लाल गेट", ["देवळाच्या", "मागे", "लाल"], "Ishaan"),
                ("देवळासमोर निळे गेट", ["देवळासमोर", "निळे"], "Zahira"),
                ("मशिदीच्या मागे निळे गेट", ["मशिदीच्या", "मागे", "निळे"], "Ishaan")],
        "M-B": [("पहिल्या गल्लीतले हिरवे घर", ["पहिल्या", "हिरवे"], "Zahira"),
                ("दुसऱ्या गल्लीतले हिरवे घर", ["दुसऱ्या", "हिरवे"], "Ishaan"),
                ("दुसऱ्या गल्लीतले पिवळे घर", ["दुसऱ्या", "पिवळे"], "Zahira"),
                ("तिसऱ्या गल्लीतले पिवळे घर", ["तिसऱ्या", "पिवळे"], "Ishaan")],
        "M-C": [("उजव्या बाजूला पहिले दुकान", ["उजव्या", "पहिले"], "Zahira"),
                ("डाव्या बाजूला पहिले दुकान", ["डाव्या", "पहिले"], "Ishaan"),
                ("उजव्या बाजूला दुसरे दुकान", ["उजव्या", "दुसरे"], "Zahira"),
                ("डाव्या बाजूला दुसरे दुकान", ["डाव्या", "दुसरे"], "Ishaan")],
    },
}
HARD_CONDS = [("clean", None, None), ("bike@10", "bike", 10), ("bike@5", "bike", 5),
              ("bike@0", "bike", 0), ("engine@5", "engine", 5), ("babble@5", "babble", 5)]
ORIG_CONDS = [("bike@10", "bike", 10), ("bike@5", "bike", 5), ("bike@0", "bike", 0)]
ACCEPT_SIM, ACCEPT_MARGIN = 0.75, 0.12


def score(ref, hyp, crit, pool, true_idx):
    r, g = norm(ref), norm(hyp)
    sims = [difflib.SequenceMatcher(None, g, p).ratio() for p in pool]
    best = max(range(len(pool)), key=lambda k: sims[k])
    others = sorted((s for k, s in enumerate(sims) if k != best), reverse=True)
    margin = sims[best] - (others[0] if others else 0)
    accepted = sims[best] >= ACCEPT_SIM and margin >= ACCEPT_MARGIN
    cw = [norm(c) in g for c in crit]
    return {
        "exact": int(r == g), "wer": round(wer(r, g), 3),
        "crit_all": int(all(cw)), "crit_share": round(sum(cw) / len(cw), 3),
        "ident": int(best == true_idx), "margin": round(margin, 3),
        "accepted": int(accepted), "wrong_accept": int(accepted and best != true_idx),
    }


def stt_safe(audio, lang):
    try:
        return gnani.stt(audio, lang)
    except gnani.ApiError as e:
        print(f"STT failed: {e}")
        if e.status in (401, 402, 403, 429):
            sys.exit("Stopping: auth, credit or rate-limit problem.")
        return None


def main():
    rows = []
    # ---- Part A: generate the 24 hard clips
    clean = {}
    for lang, groups in HARD.items():
        for gname, items in groups.items():
            for i, (phrase, crit, voice) in enumerate(items):
                try:
                    clean[(lang, gname, i)] = gnani.tts(phrase, voice, lang)
                except gnani.ApiError as e:
                    print(f"TTS failed {gname}#{i}: {e}")
                    if e.status in (401, 402, 403, 429):
                        sys.exit("Stopping: auth, credit or rate-limit problem.")
    print(f"Generated {len(clean)} hard clips", flush=True)
    # babble source: every clean clip we have, including the original 20
    babble_src = {k: noise.to_8k(v) for k, v in clean.items()}
    for lang, items in ORIG.items():
        for idx in range(len(items)):
            f = OUT / f"sweep_{lang}_{idx}.wav"
            if f.exists():
                babble_src[("orig", lang, idx)] = noise.to_8k(f.read_bytes())

    def clips_excluding(key):
        return [v for k, v in babble_src.items() if k != key]

    for lang, groups in HARD.items():
        for gname, items in groups.items():
            pool = [norm(p) for p, _, _ in items]
            for i, (phrase, crit, voice) in enumerate(items):
                key = (lang, gname, i)
                if key not in clean:
                    continue
                for cname, kind, snr in HARD_CONDS:
                    audio = clean[key] if kind is None else noise.add_noise(
                        clean[key], kind, snr, clips_excluding(key), seed=zlib.crc32(f"{gname}{i}{cname}".encode()) % 10_000)
                    hyp = stt_safe(audio, lang)
                    if hyp is None:
                        continue
                    rows.append({"part": "hard", "lang": lang, "group": gname, "idx": i, "cond": cname,
                                 "ref": phrase, "hyp": hyp, **score(phrase, hyp, crit, pool, i)})
                    time.sleep(0.2)
            print(f"hard {gname} done", flush=True)

    # ---- Part B: original 20 phrasings under bike noise
    for lang, items in ORIG.items():
        pool = [norm(p) for p, _, _ in items]
        for idx, (phrase, kws, voice) in enumerate(items):
            f = OUT / f"sweep_{lang}_{idx}.wav"
            if not f.exists():
                continue
            wav = f.read_bytes()
            key = ("orig", lang, idx)
            for cname, kind, snr in ORIG_CONDS:
                audio = noise.add_noise(wav, kind, snr, clips_excluding(key), seed=idx * 17 + snr)
                hyp = stt_safe(audio, lang)
                if hyp is None:
                    continue
                rows.append({"part": "orig", "lang": lang, "group": "orig", "idx": idx, "cond": cname,
                             "ref": phrase, "hyp": hyp, **score(phrase, hyp, kws, pool, idx)})
                time.sleep(0.2)
        print(f"orig {lang} done", flush=True)

    with open(OUT / "hard_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def table(title, sel, conds):
        print(f"\n== {title}")
        print(f"{'cond':<9}{'n':>3}{'exact%':>8}{'WER%':>6}{'crit_all%':>10}{'ident%':>8}{'accept%':>9}{'wrongAcc%':>10}")
        summ = {}
        for c in conds:
            v = [r for r in sel if r["cond"] == c]
            if not v:
                continue
            n = len(v)
            acc = sum(r["accepted"] for r in v)
            wa = sum(r["wrong_accept"] for r in v)
            m = {"n": n, "exact": round(100 * sum(r["exact"] for r in v) / n),
                 "wer": round(100 * sum(r["wer"] for r in v) / n),
                 "crit_all": round(100 * sum(r["crit_all"] for r in v) / n),
                 "ident": round(100 * sum(r["ident"] for r in v) / n),
                 "accept": round(100 * acc / n),
                 "wrong_accept_of_accepted": round(100 * wa / acc) if acc else 0}
            summ[c] = m
            print(f"{c:<9}{n:>3}{m['exact']:>8}{m['wer']:>6}{m['crit_all']:>10}{m['ident']:>8}{m['accept']:>9}{m['wrong_accept_of_accepted']:>10}")
        return summ

    hard = [r for r in rows if r["part"] == "hard"]
    orig = [r for r in rows if r["part"] == "orig"]
    names = [c[0] for c in HARD_CONDS]
    summary = {
        "hard_all": table("Hard minimal pairs, all (identification within group of 4)", hard, names),
        "hard_hi": table("Hard, Hindi", [r for r in hard if r["lang"] == "hi-IN"], names),
        "hard_mr": table("Hard, Marathi", [r for r in hard if r["lang"] == "mr-IN"], names),
        "orig_bike": table("Original 20 phrasings under bike noise (identification among 10)", orig, [c[0] for c in ORIG_CONDS]),
    }
    (OUT / "hard_summary.json").write_text(json.dumps(summary, indent=1))
    print("\nRows: out/hard_results.csv")


if __name__ == "__main__":
    main()
