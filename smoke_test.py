"""Smoke test for Gnani Prisma (STT) and Timbre (TTS).

Reads GNANI_API_KEY from the environment or a local .env file.
Never prints the key. Costs a handful of credits (about 12 API calls).
"""
import array
import io
import json
import math
import os
import random
import sys
import time
import wave
from pathlib import Path

import httpx

BASE = "https://api.vachana.ai"
HERE = Path(__file__).parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)


def load_key():
    key = os.environ.get("GNANI_API_KEY")
    env = HERE / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("GNANI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key


KEY = load_key()
if not KEY or KEY == "put_your_key_here":
    sys.exit("No key found. Run: cp .env.example .env  then put your key in .env")

HEADERS = {"X-API-Key-ID": KEY}
client = httpx.Client(timeout=60)


class ApiError(Exception):
    pass


def tts(text, voice, language, model="timbre-v2.5"):
    last = None
    for rate in (16000, 48000):
        body = {
            "text": text,
            "voice": voice,
            "model": model,
            "language": language,
            "speed": 1.0,
            "audio_config": {
                "sample_rate": rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        r = client.post(
            f"{BASE}/api/v1/tts/inference",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=body,
        )
        if r.status_code == 200 and r.content[:4] == b"RIFF":
            return r.content
        last = f"HTTP {r.status_code} at {rate} Hz: {r.text[:200]}"
        if r.status_code in (401, 403, 429):
            break
    raise ApiError(last)


def stt(wav_bytes, language, fmt=None, native=False):
    data = {"language_code": language}
    if fmt:
        data["format"] = fmt
    if native:
        data["itn_native_numerals"] = "true"
    r = client.post(
        f"{BASE}/stt/v3",
        headers=HEADERS,
        files={"audio_file": ("audio.wav", wav_bytes, "audio/wav")},
        data=data,
    )
    if r.status_code != 200:
        raise ApiError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("transcript", "")


def read_wav(b):
    with wave.open(io.BytesIO(b)) as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    assert sw == 2, "expected 16-bit audio"
    s = array.array("h")
    s.frombytes(raw)
    if ch > 1:
        s = s[::ch]
    return list(s), sr


def write_wav(samples, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(array.array("h", samples).tobytes())
    return buf.getvalue()


def degrade(wav_bytes, snr_db=10, target_sr=8000):
    """Resample to 8 kHz and add white noise at the given SNR."""
    s, sr = read_wav(wav_bytes)
    n_out = int(len(s) * target_sr / sr)
    out = []
    for i in range(n_out):
        pos = i * sr / target_sr
        j = int(pos)
        frac = pos - j
        a = s[j]
        b = s[min(j + 1, len(s) - 1)]
        out.append(a + (b - a) * frac)
    rms = math.sqrt(sum(x * x for x in out) / max(len(out), 1)) or 1.0
    noise_rms = rms / (10 ** (snr_db / 20))
    rnd = random.Random(7)
    noisy = [max(-32768, min(32767, int(x + rnd.gauss(0, noise_rms)))) for x in out]
    return write_wav(noisy, target_sr)


RESULTS = []


def run(name, fn):
    t0 = time.time()
    try:
        res = fn()
        status = "ok"
    except Exception as e:
        res, status = str(e), "ERROR"
    dt = time.time() - t0
    RESULTS.append({"test": name, "status": status, "seconds": round(dt, 1), "result": res})
    print(f"[{status}] {name} ({dt:.1f}s)\n    {res}\n")
    if status == "ERROR" and any(c in str(res) for c in ("HTTP 401", "HTTP 403")):
        print("Auth or credit problem. Check your key and credit balance.")
        finish()
    time.sleep(1)


def finish():
    (OUT / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    ok = sum(r["status"] == "ok" for r in RESULTS)
    print(f"{ok}/{len(RESULTS)} tests returned a response. Details: out/results.json")
    sys.exit(0)


audio = {}


def make(name, text, voice, lang):
    audio[name] = tts(text, voice, lang)
    (OUT / f"{name}.wav").write_bytes(audio[name])
    s, sr = read_wav(audio[name])
    return f"{len(s) / sr:.1f}s audio at {sr} Hz"


HI = "mandir ke peeche neela gate"
HI_DEV = "मंदिर के पीछे नीला गेट"

run("1 timbre hindi tts", lambda: make("hi", HI_DEV, "Nalini", "hi-IN"))
run("2 prisma hindi clean (verbatim)", lambda: f"expected: {HI_DEV} | got: {stt(audio['hi'], 'hi-IN', 'verbatim')}")
run("3 prisma hindi clean (transcribe)", lambda: f"got: {stt(audio['hi'], 'hi-IN', 'transcribe')}")


def noisy(snr):
    wav = degrade(audio["hi"], snr_db=snr)
    (OUT / f"hi_8k_snr{snr}.wav").write_bytes(wav)
    return f"expected: {HI_DEV} | got: {stt(wav, 'hi-IN', 'verbatim')}"


run("4 prisma hindi 8kHz + noise 10 dB", lambda: noisy(10))
run("5 prisma hindi 8kHz + noise 0 dB", lambda: noisy(0))

NUMS = [
    ("sava do lakh rupaye", "सवा दो लाख रुपये"),
    ("dedh sau", "डेढ़ सौ"),
    ("pachpan", "पचपन"),
    ("pachees", "पच्चीस"),
]
for i, (label, dev) in enumerate(NUMS):
    def num_test(label=label, dev=dev, i=i):
        make(f"num{i}", dev, "Nalini", "hi-IN")
        v = stt(audio[f"num{i}"], "hi-IN", "verbatim")
        t = stt(audio[f"num{i}"], "hi-IN", "transcribe")
        return f"said: {dev} | verbatim: {v} | transcribe: {t}"
    run(f"{6 + i} numbers: {label}", num_test)

run("10 timbre marathi tts", lambda: make("mr", "देवळाच्या मागे निळे गेट", "Zahira", "mr-IN"))
run("11 prisma marathi", lambda: f"expected: देवळाच्या मागे निळे गेट | got: {stt(audio['mr'], 'mr-IN', 'verbatim')}")
run("12 timbre hinglish tts", lambda: make("hien", "temple ke peeche blue gate", "Poorvi", "hi-en"))
run("13 prisma hinglish (en-IN)", lambda: f"expected: temple ke peeche blue gate | got: {stt(audio['hien'], 'en-IN')}")

finish()
