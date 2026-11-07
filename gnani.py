"""Shared helpers for the Gnani Prisma (STT) and Timbre (TTS) REST APIs."""
import array
import io
import math
import os
import random
import threading
import time
import wave
from pathlib import Path

import httpx

BASE = "https://api.vachana.ai"
HERE = Path(__file__).parent


class ApiError(Exception):
    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


def load_key():
    key = os.environ.get("GNANI_API_KEY")
    env = HERE / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("GNANI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key or key == "put_your_key_here":
        raise SystemExit("No key found in .env")
    return key


_client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
RETRIES, BACKOFF = 3, 2.0
_headers = None


def headers():
    global _headers
    if _headers is None:
        _headers = {"X-API-Key-ID": load_key()}
    return _headers



# The account allows ONE active request at a time (HTTP 429 "Only 1 active request is allowed at a time" otherwise), so every call in
# this process goes through one lock. A 429 caused by another process using the same key is retried after a short wait.
_api_lock = threading.Lock()
RATE_RETRIES, RATE_WAIT = 5, 0.7


def _post(url, **kw):
    """POST with retries on timeouts, connection errors, 5xx and 429. One request at a time. Raises ApiError when it gives up."""
    last, tries, rate_tries = None, 0, 0
    while tries < RETRIES:
        try:
            with _api_lock:
                r = _client.post(url, **kw)
            if r.status_code == 429 and rate_tries < RATE_RETRIES:
                rate_tries += 1
                time.sleep(RATE_WAIT * rate_tries)
                continue
            if r.status_code < 500:
                return r
            last = f"HTTP {r.status_code}: {r.text[:120]}"
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = f"{type(e).__name__}: {e}"
        tries += 1
        if tries < RETRIES:
            time.sleep(BACKOFF * tries)
    raise ApiError(f"gave up after {RETRIES} tries ({last})", None)


def tts(text, voice, language, model="timbre-v2.5", rate=16000):
    body = {
        "text": text, "voice": voice, "model": model, "language": language, "speed": 1.0,
        "audio_config": {"sample_rate": rate, "num_channels": 1, "sample_width": 2,
                         "encoding": "linear_pcm", "container": "wav"},
    }
    r = _post(f"{BASE}/api/v1/tts/inference",
                     headers={**headers(), "Content-Type": "application/json"}, json=body)
    if r.status_code == 200 and r.content[:4] == b"RIFF":
        return r.content
    raise ApiError(f"TTS HTTP {r.status_code}: {r.text[:160]}", r.status_code)


def stt(wav_bytes, language, fmt="verbatim"):
    r = _post(f"{BASE}/stt/v3", headers=headers(),
                     files={"audio_file": ("audio.wav", wav_bytes, "audio/wav")},
                     data={"language_code": language, "format": fmt})
    if r.status_code != 200:
        raise ApiError(f"STT HTTP {r.status_code}: {r.text[:160]}", r.status_code)
    return r.json().get("transcript", "")


def read_wav(b):
    with wave.open(io.BytesIO(b)) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    s = array.array("h")
    s.frombytes(raw)
    return (list(s[::ch]) if ch > 1 else list(s)), sr


def write_wav(samples, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(array.array("h", samples).tobytes())
    return buf.getvalue()


def degrade(wav_bytes, snr_db, target_sr=8000, seed=7):
    """Resample to 8 kHz and add white noise at the given signal-to-noise ratio."""
    s, sr = read_wav(wav_bytes)
    n_out = int(len(s) * target_sr / sr)
    out = []
    for i in range(n_out):
        pos = i * sr / target_sr
        j = int(pos)
        a, b = s[j], s[min(j + 1, len(s) - 1)]
        out.append(a + (b - a) * (pos - j))
    rms = math.sqrt(sum(x * x for x in out) / max(len(out), 1)) or 1.0
    noise_rms = rms / (10 ** (snr_db / 20))
    rnd = random.Random(seed)
    noisy = [max(-32768, min(32767, int(x + rnd.gauss(0, noise_rms)))) for x in out]
    return write_wav(noisy, target_sr)


def pad_silence(wav_bytes, secs=0.6):
    """Add silence on both sides. One-word replies (e.g. Marathi 'हो', 'नाही') came back empty without it."""
    s, sr = read_wav(wav_bytes)
    z = [0] * int(sr * secs)
    return write_wav(z + s + z, sr)


def check_network(host="api.vachana.ai", timeout=8.0):
    """Fail fast when DNS or the network is down. httpx timeouts do not cover DNS lookups, so a
    dead resolver otherwise hangs a run forever. Returns (ok, message)."""
    import socket
    import threading

    box = {}

    def probe():
        try:
            socket.create_connection((host, 443), timeout=timeout).close()
            box["ok"] = True
        except OSError as e:
            box["err"] = str(e)

    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(timeout + 1)
    if box.get("ok"):
        return True, "ok"
    return False, box.get("err") or f"no response from {host} within {timeout:.0f}s (DNS or network down?)"


def pad_if_short(wav_bytes, min_secs=1.2, secs=0.6):
    """Pad only clips shorter than min_secs: one-word replies need it, and padding a longer clip
    changed its transcript in testing."""
    s, sr = read_wav(wav_bytes)
    return wav_bytes if len(s) / sr >= min_secs else pad_silence(wav_bytes, secs)
