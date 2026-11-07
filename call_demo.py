"""Two-person call demo: a Hindi-speaking customer and a Kannada-speaking biker, with an interpreter in between.

Everything is synthetic: the customer and biker voices are Gnani Timbre, the customer's line has simulated phone-line noise and
the biker's has simulated bike noise. Prisma transcribes each turn, translate.py (rule-based, no LLM) translates what it can
recognise, and Timbre speaks the result to the other person. What it cannot translate is refused out loud.

    python call_demo.py          # responses are cached in out/call/cache, so repeats are free
    python build_call_page.py    # writes out/call/index.html
"""
import json
import sys
import time
import zlib
from pathlib import Path

import gnani
import noise
from demo import LiveApi
from translate import translate

OUT = gnani.HERE / "out" / "call"
PEOPLE = {   # who speaks which language, and the voice that stands in for them
    "customer": {"lang": "hi-IN", "voice": "Deepak", "label": "Customer", "language": "Hindi", "line": "phone line, 20 dB noise"},
    "biker": {"lang": "kn-IN", "voice": "Kavin", "label": "Biker", "language": "Kannada", "line": "bike noise, 5 dB"},
}
INTERPRETER = {"hi-IN": "Nalini", "kn-IN": "Saanvi"}      # the voice that speaks the translation, in the listener's language
OTHER = {"customer": "biker", "biker": "customer"}
SCRIPT = [
    dict(who="customer", text="भैया ये गेट दूसरा गेट दायीं तरफ वाला", note="the example sentence from the brief"),
    dict(who="biker", text="ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್", note="the biker reads it back"),
    dict(who="customer", text="हाँ, सही है", note="the customer confirms"),
    dict(who="biker", text="ಸಿಕ್ಕಿತು", note="the biker found it"),
    dict(who="customer", text="भैया मैं पांच मिनट में आ रहा हूँ दूसरा गेट दायीं तरफ", note="limit: only the landmark part is understood"),
    dict(who="customer", text="भैया चाय पीकर आना", note="limit: ordinary conversation cannot be translated"),
]


def seed(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode()) % 100_000


def run(api, out_dir=OUT, script=SCRIPT, extra_babble=()):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for f in list(out.glob("turn*.wav")) + [out / "call_sequence.wav"]:
        if f.exists():
            f.unlink()
    seq, babble = [], [noise.to_8k(Path(p).read_bytes()) for p in extra_babble]
    res = {"people": PEOPLE, "interpreter": INTERPRETER, "turns": []}

    def save(name, wav):
        (out / name).write_bytes(wav)
        return name

    for n, step in enumerate(script, 1):
        who = step["who"]
        p, other = PEOPLE[who], PEOPLE[OTHER[who]]
        clean = api.tts(step["text"], p["voice"], p["lang"], hint=step["text"])
        babble.append(noise.to_8k(clean))
        if who == "customer":
            audio = gnani.degrade(clean, 20, seed=seed("call", n))
        else:
            audio = gnani.pad_if_short(noise.add_noise(clean, "bike", 5, babble[:-1] or babble, seed=seed("call", n)))
        said_audio = save(f"turn{n}_said.wav", audio)
        seq.append((f"turn {n}: {who}", audio))
        heard = api.stt(audio, p["lang"], hint=step["text"], ctx={"turn": n})
        r = translate(heard, p["lang"], other["lang"])

        spoken = []

        def speak(to, text, kind):
            lang = PEOPLE[to]["lang"]
            wav = api.tts(text, INTERPRETER[lang], lang, hint=text)
            name = save(f"turn{n}_out{len(spoken) + 1}_{kind}.wav", wav)
            seq.append((f"turn {n}: interpreter to {to}", wav))
            spoken.append({"to": to, "lang": lang, "voice": INTERPRETER[lang], "kind": kind, "text": text, "audio": name})

        if r.status in ("translated", "partial"):
            speak(OTHER[who], r.output, "translation")
            if r.status == "partial":
                speak(OTHER[who], r.notice_to_listener, "notice")
        else:
            speak(who, r.notice_to_speaker, "notice")
            speak(OTHER[who], r.notice_to_listener, "notice")
        res["turns"].append({
            "n": n, "who": who, "note": step["note"], "src": p["lang"], "dst": other["lang"], "line": p["line"],
            "said": step["text"], "said_audio": said_audio, "heard": heard,
            "status": r.status, "output": r.output, "english": r.english, "reason": r.reason, "reason_text": r.reason_text,
            "intents": r.intents, "not_understood": r.untranslated, "spoken": spoken,
        })
    (out / "call_sequence.wav").write_bytes(__import__("demo").join_wavs(seq))
    res["calls"] = dict(getattr(api, "calls", {}))
    (out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main():
    ok, why = gnani.check_network()
    if not ok:
        sys.exit(f"Cannot reach api.vachana.ai ({why}). Cached responses in out/call/cache are reused once you are online.")
    api = LiveApi(OUT / "cache")
    extra = sorted((gnani.HERE / "out").glob("sweep_hi-IN_[0-4].wav"))        # other voices, used as background babble
    try:
        res = run(api, OUT, extra_babble=extra)
    except (gnani.ApiError, OSError) as e:
        sys.exit(f"API error: {e}\nEvery call that succeeded is cached in {OUT}/cache; run the same command again to resume.")
    for t in res["turns"]:
        print(f"turn {t['n']} {t['who']:<8} said {t['said']!r}\n   Prisma heard {t['heard']!r}\n   -> {t['status']}: {t['output'] or t['reason_text']!r}"
              + (f"   (not understood: {t['not_understood']})" if t["not_understood"] else ""))
    print(f"\nlive API calls: {res['calls']}   files in {OUT}")


if __name__ == "__main__":
    main()
