"""Noise sweep: 20 landmark phrasings (10 Hindi, 10 Marathi) x 5 conditions.

Per condition it reports:
  exact     transcript equals the phrase after normalisation
  wer       word error rate (token edit distance / reference tokens)
  keywords  share of landmark keywords found in the transcript
  ident     closed-vocab test: the transcript is matched against the 10 phrases
            of its language by string similarity; correct if the best match is the truth
All audio is synthetic (Timbre) with white noise added; real noise will be harder.
"""
import csv
import difflib
import json
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import gnani

OUT = gnani.HERE / "out"
OUT.mkdir(exist_ok=True)

# (phrase, [landmark keywords], voice)
PHRASES = {
    "hi-IN": [
        ("मंदिर के पीछे नीला गेट", ["मंदिर", "नीला", "गेट"], "Nalini"),
        ("पेट्रोल पंप के सामने वाली गली", ["पेट्रोल", "पंप", "गली"], "Deepak"),
        ("स्कूल के बगल में लाल मकान", ["स्कूल", "लाल", "मकान"], "Nalini"),
        ("बड़े पीपल के पेड़ के नीचे", ["पीपल", "पेड़"], "Deepak"),
        ("दूसरी गली में हरे रंग का दरवाज़ा", ["दूसरी", "हरे", "दरवाज"], "Nalini"),
        ("मस्जिद के सामने किराने की दुकान", ["मस्जिद", "किराने", "दुकान"], "Deepak"),
        ("पानी की टंकी के पास पीला घर", ["पानी", "टंकी", "पीला", "घर"], "Nalini"),
        ("बस स्टैंड से सीधे जाकर दाएं मुड़िए", ["स्टैंड", "सीधे", "दाएं"], "Deepak"),
        ("हनुमान मंदिर के बाद तीसरा मकान", ["हनुमान", "मंदिर", "तीसरा", "मकान"], "Nalini"),
        ("पोस्ट ऑफिस के ऊपर वाला फ्लैट", ["पोस्ट", "ऑफिस", "ऊपर", "फ्लैट"], "Deepak"),
    ],
    "mr-IN": [
        ("देवळाच्या मागे निळे गेट", ["देवळाच्या", "निळे", "गेट"], "Zahira"),
        ("पेट्रोल पंपासमोरची गल्ली", ["पेट्रोल", "पंपासमोरची", "गल्ली"], "Ishaan"),
        ("शाळेच्या शेजारी लाल घर", ["शाळेच्या", "शेजारी", "लाल", "घर"], "Zahira"),
        ("मोठ्या वडाच्या झाडाखाली", ["मोठ्या", "वडाच्या", "झाडाखाली"], "Ishaan"),
        ("दुसऱ्या गल्लीतला हिरवा दरवाजा", ["दुसऱ्या", "गल्लीतला", "हिरवा", "दरवाजा"], "Zahira"),
        ("मशिदीसमोर किराणा दुकान", ["मशिदीसमोर", "किराणा", "दुकान"], "Ishaan"),
        ("पाण्याच्या टाकीजवळ पिवळे घर", ["पाण्याच्या", "टाकीजवळ", "पिवळे", "घर"], "Zahira"),
        ("बस स्टँडपासून सरळ जाऊन उजवीकडे वळा", ["स्टँडपासून", "सरळ", "उजवीकडे", "वळा"], "Ishaan"),
        ("मारुती मंदिरानंतर तिसरे घर", ["मारुती", "मंदिरानंतर", "तिसरे", "घर"], "Zahira"),
        ("पोस्ट ऑफिसच्या वरचा फ्लॅट", ["पोस्ट", "ऑफिसच्या", "वरचा", "फ्लॅट"], "Ishaan"),
    ],
}
CONDITIONS = ["clean", "20dB", "10dB", "5dB", "0dB"]
SNR = {"20dB": 20, "10dB": 10, "5dB": 5, "0dB": 0}


def norm(s):
    s = unicodedata.normalize("NFC", s).replace("़", "")
    for ch in "।,.?!-–\"'":
        s = s.replace(ch, " ")
    return " ".join(s.lower().split())


def wer(ref, hyp):
    r, h = ref.split(), hyp.split()
    d = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hw in enumerate(h, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rw != hw))
    return d[len(h)] / max(len(r), 1)


def main():
    rows = []
    calls = 0
    for lang, items in PHRASES.items():
        pool = [norm(p) for p, _, _ in items]
        for idx, (phrase, kws, voice) in enumerate(items):
            try:
                clean = gnani.tts(phrase, voice, lang)
                calls += 1
            except gnani.ApiError as e:
                print(f"TTS failed for {lang} #{idx}: {e}")
                if e.status in (401, 403, 429):
                    sys.exit("Stopping: auth, credit or rate-limit problem.")
                continue
            (OUT / f"sweep_{lang}_{idx}.wav").write_bytes(clean)
            for cond in CONDITIONS:
                audio = clean if cond == "clean" else gnani.degrade(clean, SNR[cond], seed=idx * 31 + SNR[cond])
                try:
                    hyp = gnani.stt(audio, lang)
                    calls += 1
                except gnani.ApiError as e:
                    print(f"STT failed {lang} #{idx} {cond}: {e}")
                    if e.status in (401, 403, 429):
                        sys.exit("Stopping: auth, credit or rate-limit problem.")
                    continue
                ref, got = norm(phrase), norm(hyp)
                best = max(range(len(pool)), key=lambda k: difflib.SequenceMatcher(None, got, pool[k]).ratio())
                rows.append({
                    "lang": lang, "idx": idx, "voice": voice, "cond": cond,
                    "ref": phrase, "hyp": hyp,
                    "exact": int(ref == got),
                    "wer": round(wer(ref, got), 3),
                    "kw": round(sum(norm(k) in got for k in kws) / len(kws), 3),
                    "ident": int(best == idx),
                })
                time.sleep(0.25)
            print(f"{lang} #{idx} done ({calls} calls so far)", flush=True)

    with open(OUT / "sweep_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def summarise(sel):
        g = defaultdict(list)
        for r in sel:
            g[r["cond"]].append(r)
        out = {}
        for c in CONDITIONS:
            v = g.get(c, [])
            n = len(v)
            if n:
                out[c] = {
                    "n": n,
                    "exact_%": round(100 * sum(r["exact"] for r in v) / n),
                    "wer_%": round(100 * sum(r["wer"] for r in v) / n),
                    "keywords_%": round(100 * sum(r["kw"] for r in v) / n),
                    "ident_%": round(100 * sum(r["ident"] for r in v) / n),
                }
        return out

    summary = {"all": summarise(rows)}
    for lang in PHRASES:
        summary[lang] = summarise([r for r in rows if r["lang"] == lang])
    (OUT / "sweep_summary.json").write_text(json.dumps(summary, indent=1))

    for name, s in summary.items():
        print(f"\n== {name}")
        print(f"{'condition':<8} {'n':>3} {'exact%':>7} {'WER%':>6} {'keywords%':>10} {'ident%':>7}")
        for c, m in s.items():
            print(f"{c:<8} {m['n']:>3} {m['exact_%']:>7} {m['wer_%']:>6} {m['keywords_%']:>10} {m['ident_%']:>7}")
    print(f"\n{calls} API calls. Rows: out/sweep_results.csv")


if __name__ == "__main__":
    main()
