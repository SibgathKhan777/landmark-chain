"""Bike-like noise: low-frequency engine hum, speech babble, and a mix of both. Pure Python."""
import math
import random

import gnani

SR = 8000


def to_8k(wav_bytes):
    s, sr = gnani.read_wav(wav_bytes)
    n_out = int(len(s) * SR / sr)
    out = []
    for i in range(n_out):
        pos = i * sr / SR
        j = int(pos)
        a, b = s[j], s[min(j + 1, len(s) - 1)]
        out.append(a + (b - a) * (pos - j))
    return out


def rms(x):
    return math.sqrt(sum(v * v for v in x) / max(len(x), 1)) or 1.0


def unit(x):
    r = rms(x)
    return [v / r for v in x]


def engine(n, rnd):
    f0 = rnd.uniform(60, 90)
    am_f = rnd.uniform(5, 9)
    ph = [rnd.uniform(0, 6.283) for _ in range(8)]
    brown, b = [], 0.0
    for _ in range(n):
        b = 0.995 * b + rnd.gauss(0, 0.1)
        brown.append(b)
    out = []
    for i in range(n):
        t = i / SR
        am = 1 + 0.3 * math.sin(6.283 * am_f * t)
        h = sum(math.sin(6.283 * f0 * (k + 1) * t + ph[k]) / (k + 1) for k in range(8))
        out.append(am * h + 2.0 * brown[i])
    return unit(out)


def babble(n, clips, rnd, voices=4):
    mix = [0.0] * n
    for c in rnd.sample(clips, min(voices, len(clips))):
        off = rnd.randrange(len(c))
        v = unit([c[(off + i) % len(c)] for i in range(n)])
        mix = [a + b for a, b in zip(mix, v)]
    return unit(mix)


def make_noise(kind, n, clips, rnd):
    if kind == "engine":
        return engine(n, rnd)
    if kind == "babble":
        return babble(n, clips, rnd)
    e, b = engine(n, rnd), babble(n, clips, rnd)
    return unit([0.9 * x + 0.4 * y for x, y in zip(e, b)])


def add_noise(wav_bytes, kind, snr_db, clips, seed):
    rnd = random.Random(seed)
    sig = to_8k(wav_bytes)
    noise = make_noise(kind, len(sig), clips, rnd)
    scale = rms(sig) / (10 ** (snr_db / 20))
    mixed = [s + n * scale for s, n in zip(sig, noise)]
    peak = max(abs(v) for v in mixed) or 1.0
    gain = min(1.0, 30000 / peak)
    out = [int(v * gain) for v in mixed]
    return gnani.write_wav(out, SR)
