"""A live call between two windows, with an interpreter in the middle. Gnani Prisma (speech to text) and Timbre (text to speech)
plus the rule-based translator in translate.py. By default no LLM and no machine translation; an optional AI fallback (llm_fallback.py)
is off unless LLM_BASE_URL is set.

    python live_call.py            # then open http://127.0.0.1:8770/  (both windows) or /phone?role=customer and /phone?role=biker

How a turn works (utterance level, not streaming):
    speaker's audio -> Prisma -> translate.py -> Timbre -> the OTHER window only

* Each window receives audio and captions in ONE language only: its own (Hindi or Kannada), or English if the person chose it.
  The speaker's original voice is never sent to the other window. The speaker's own window gets a caption of what Prisma heard.
* The "stage" view also sees everything (English meaning, timings), as an operator console. No caller hears it.
* Every turn is timed: Prisma, rules, Timbre, and the total from the end of the utterance to the translated audio being ready.
* The API key stays on this server. The browser never sees it.

The scripted call uses synthetic Timbre voices (the contest allows synthetic data only). The microphone button sends YOUR voice
to Gnani's API, so use it for your own testing, not in the contest video.
"""
import argparse
import json
import math
import os
import queue
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import gnani
import llm_fallback
import noise
from translate import NOTICE, translate

HERE = Path(__file__).resolve().parent
WEB = HERE / "live"
OUT = HERE / "out" / "live"
SHARED_CLIPS = HERE / "demos" / "clips"          # the saved demo's synthetic voices

ROLES = {
    "customer": {"lang": "hi-IN", "voice": "Deepak", "label": "Customer", "language": "Hindi", "line": "phone line, 20 dB noise", "person": "Arun"},
    "biker": {"lang": "kn-IN", "voice": "Kavin", "label": "Biker", "language": "Kannada", "line": "bike noise, 5 dB", "person": "Manju"},   # invented names
}
# The same two people in a second call: the customer speaks English and the biker speaks Hindi. "lang" is what translate.py calls the language,
# "stt" and "tts" are the codes Gnani wants (English is en-IN).
ROLES_EN = {
    "customer": {"lang": "en", "stt": "en-IN", "tts": "en-IN", "voice": "Deepak", "label": "Customer", "language": "English", "line": "phone line, 20 dB noise", "person": "Arun"},
    "biker": {"lang": "hi-IN", "voice": "Kavin", "label": "Biker", "language": "Hindi", "line": "bike noise, 5 dB", "person": "Manju"},
}
ROLE_SETS = {"kn": ROLES, "en": ROLES_EN}
OTHER = {"customer": "biker", "biker": "customer"}
INTERPRETER = {"hi-IN": "Nalini", "kn-IN": "Saanvi", "en": "Yashvi"}       # who speaks the translation, by the listener's language
TTS_LANG = {"hi-IN": "hi-IN", "kn-IN": "kn-IN", "en": "en-IN"}
COVERAGE_MIN = 0.9          # with the AI on, a rules fragment is spoken on its own only if the rules understood at least this share of the words
MAX_BODY = 4_000_000                                                       # about two minutes of 16 kHz mono audio

SCRIPT = [   # synthetic voices; the first line is the sentence from the brief, as Prisma writes it. Four turns so the video fits in 60 s
    dict(who="customer", text="भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ"),
    dict(who="biker", text="ಕಟ್ಟಡ ಕಾಣಿಸಿತು"),
    dict(who="customer", text="भैया मैं पांच मिनट में आ रहा हूँ"),
    dict(who="customer", text="भैया चाय पीकर आना"),
]


SCRIPT_REAL = [   # a delivery call that goes the way they do: hello, "where are you", lost, directions, found it. Needs the AI fallback for the casual lines.
    dict(who="customer", text="हेलो भैया, आप कहाँ हो?"),
    dict(who="biker", text="ಅಣ್ಣಾ ನಾನು ಮುಖ್ಯ ರಸ್ತೆಯಲ್ಲಿ ಇದ್ದೀನಿ, ಅಡ್ರೆಸ್ ಸಿಗ್ತಿಲ್ಲ"),
    dict(who="customer", text="भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ"),
    dict(who="biker", text="ಕಟ್ಟಡ ಕಾಣಿಸಿತು ಅಣ್ಣಾ"),
    dict(who="customer", text="हाँ वही है, मैं तीसरे फ्लोर पर हूँ, नीला दरवाजा है"),
    dict(who="biker", text="ಸರಿ ಅಣ್ಣಾ, ಬರ್ತಾ ಇದ್ದೀನಿ"),
]
SCRIPT_EN = [   # the customer speaks English, the biker speaks Hindi. Rules only: no AI needed. Same shape as the default call: a translation, a reply, a partial, a refusal
    dict(who="customer", text="Go straight, take a right, then you will see a building ahead. Wait there."),
    dict(who="biker", text="बिल्डिंग दिख गई भैया"),
    dict(who="customer", text="Wait there, I will be down in five minutes."),
    dict(who="customer", text="Please bring some water."),
]
SCRIPTS = {"default": SCRIPT, "real": SCRIPT_REAL, "english": SCRIPT_EN}
SCRIPT_ROLES = {"default": "kn", "real": "kn", "english": "en"}          # which pair of languages each script is played in


def seed(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode()) % 100_000


def duration(wav):
    samples, sr = gnani.read_wav(wav)
    return len(samples) / sr


def level(wav):
    """How loud a recording is: peak and average level as a share or dB of full scale, and how much of it is clipped."""
    samples, _ = gnani.read_wav(wav)
    if not samples:
        return {"peak_pct": 0.0, "rms_dbfs": -99.0, "clipped_pct": 0.0}
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    return {"peak_pct": round(100 * max(abs(x) for x in samples) / 32768, 1), "rms_dbfs": round(20 * math.log10(max(rms, 1) / 32768), 1),
            "clipped_pct": round(100 * sum(abs(x) >= 32700 for x in samples) / len(samples), 2)}


class GnaniApi:
    """The real thing: one call per stage, never cached. Counts its calls so a run can say how many it made."""

    def __init__(self):
        self.calls = {"tts": 0, "stt": 0}

    def tts(self, text, voice, lang):
        self.calls["tts"] += 1
        return gnani.tts(text, voice, lang)

    def stt(self, wav, lang):
        self.calls["stt"] += 1
        return gnani.stt(wav, lang)


class CallRoom:
    """One call between a customer and a biker. Holds the state and does the relay; knows nothing about HTTP."""

    def __init__(self, api, clock=time.perf_counter, sleep=time.sleep, biker_snr=5, llm=None):
        self.api, self.clock, self.sleep, self.biker_snr, self.llm = api, clock, sleep, biker_snr, llm       # llm: an LlmFallback, or None (off)
        self.lock = threading.RLock()
        self.subs = {"customer": [], "biker": [], "stage": []}
        self.prefs = {"customer": "native", "biker": "native"}        # native | en: the language each person HEARS
        self.roles_key, self.roles = "kn", ROLES                      # who speaks what in this call (see ROLE_SETS)
        self.state = "idle"                                           # idle | ringing | connected | ended
        self.history, self.audio, self.turns = [], {}, 0
        self.script_running = False
        self.stop_flag = threading.Event()

    # ------------------------------------------------------------------------------------------ events
    def subscribe(self, role):
        q = queue.Queue()
        with self.lock:
            self.subs[role].append(q)
            q.put(self.snapshot(role))
        return q

    def unsubscribe(self, role, q):
        with self.lock:
            if q in self.subs[role]:
                self.subs[role].remove(q)

    def publish(self, role, event):
        event = {**event, "at": time.time()}
        with self.lock:
            for q in self.subs[role]:
                q.put(event)

    def snapshot(self, role):
        roles = self.roles
        mine = role if role in roles else None
        hist = [h for h in self.history[-12:]] if role == "stage" else []
        return {"type": "snapshot", "state": self.state, "prefs": dict(self.prefs), "role": role, "history": hist,
                "script_running": self.script_running, "you": roles.get(mine), "other": roles.get(OTHER.get(mine)), "roles": self.role_names(),
                "biker_snr": self.biker_snr, "llm": {"enabled": bool(self.llm), "name": llm_fallback.NAME if self.llm else "", "guard": bool(self.llm and getattr(self.llm, "guard_on", True)),
                                                                                              "replay": bool(self.llm and getattr(self.llm, "replay", False))}}

    def put_audio(self, wav):
        with self.lock:
            key = f"{len(self.audio) + 1}"
            self.audio[key] = wav
            if len(self.audio) > 300:
                self.audio.pop(next(iter(self.audio)))
        return f"/audio/{key}.wav"

    # ------------------------------------------------------------------------------------------ call state
    def role_names(self):
        return {r: {k: v for k, v in p.items() if k in ("person", "label", "language")} for r, p in self.roles.items()}

    def set_state(self, state):
        with self.lock:
            self.state = state
        for r in ("customer", "biker", "stage"):
            self.publish(r, {"type": "call", "state": state, "script_running": self.script_running, "roles": self.role_names()})

    def start_call(self, roles="kn"):
        with self.lock:
            if self.state in ("ringing", "connected"):
                return False
            self.history, self.turns = [], 0
            self.roles_key, self.roles = roles, ROLE_SETS[roles]
        self.set_state("ringing")
        return True

    def answer(self):
        with self.lock:
            if self.state != "ringing":
                return False
        self.set_state("connected")
        return True

    def end_call(self):
        self.stop_flag.set()
        self.set_state("ended")

    def set_pref(self, role, hear):
        if role not in self.roles or hear not in ("native", "en"):
            raise ValueError("role must be customer or biker, hear must be native or en")
        self.prefs[role] = hear
        for r in ("customer", "biker", "stage"):
            self.publish(r, {"type": "prefs", "prefs": dict(self.prefs)})

    # ------------------------------------------------------------------------------------------ one turn
    def process(self, who, wav, source="mic", original_url=None, said=None):
        """Prisma -> rules -> Timbre -> the listener's window. Returns the turn record. Raises RuntimeError if not connected."""
        if self.state != "connected":
            raise RuntimeError("the call is not connected")
        if who not in self.roles:
            raise ValueError("who must be customer or biker")
        listener = OTHER[who]
        roles = self.roles
        src = roles[who]["lang"]
        dst = "en" if self.prefs[listener] == "en" else roles[listener]["lang"]
        with self.lock:
            self.turns += 1
            n = self.turns
        t0 = self.clock()
        heard = self.api.stt(wav, roles[who].get("stt", src)).strip()
        t1 = self.clock()
        r = translate(heard, src, dst)
        t2 = self.clock()

        # The rules go first. Only when they could not translate the whole sentence, and only for Hindi/Hinglish to Kannada or English, or Kannada to Hindi or English,
        # the optional AI is asked, and its answer is used only if guard.py finds the route details matching the source.
        ai, tl = None, t2
        if self.llm and heard and llm_fallback.supported(src, dst) and r.status != "translated":
            ai = self.llm.translate(heard, dst, src)
            tl = self.clock()
        ai_ok = bool(ai and ai["status"] == "ok")

        silent = not heard
        spk_lang = "en" if self.prefs[who] == "en" else src            # a refusal notice follows the language the speaker chose to hear
        # With the AI on, a partial translation by the rules stands only if they understood enough of the sentence; a small fragment is not spoken.
        low = bool(self.llm) and llm_fallback.supported(src, dst) and not ai_ok and r.status == "partial" and r.coverage < COVERAGE_MIN
        refused = r.status == "untranslated" or low
        if ai_ok:
            to_listener, to_speaker = [ai["output"]], []
        else:
            notice = NOTICE[dst]["listener"] if low else r.notice_to_listener
            to_listener = [] if silent else ([r.output] if not refused else []) + ([notice] if notice else [])
            to_speaker = [NOTICE[spk_lang]["speaker"]] if (r.status == "untranslated" and r.notice_to_speaker) or low else []
        jobs = [(listener, t, dst) for t in to_listener] + [(who, t, spk_lang) for t in to_speaker]
        clips = [self.api.tts(t, INTERPRETER[lang], TTS_LANG[lang]) for _, t, lang in jobs]     # one at a time: the account allows one request
        t3 = self.clock()

        urls = {"listener": [], "speaker": []}
        play_s = {"listener": 0.0, "speaker": 0.0}
        for (who_to, text, lang), clip in zip(jobs, clips):
            side = "listener" if who_to == listener else "speaker"
            urls[side].append({"url": self.put_audio(clip), "text": text, "lang": lang})
            play_s[side] += duration(clip)
        rec = {
            "n": n, "who": who, "listener": listener, "source": source, "said": said, "src": src, "dst": dst, "heard": heard,
            "status": "silent" if silent else (("ai" if ai.get("checked", True) else "ai_unchecked") if ai_ok else "untranslated" if low else r.status),
            "output": ai["output"] if ai_ok else "" if low else r.output, "english": "" if ai_ok or low else r.english,
            "reason": "" if ai_ok else "low_coverage" if low else r.reason,
            "reason_text": "" if ai_ok else (f"the rules understood only {round(100 * r.coverage)}% of the words and the AI's answer was not usable, "
                                             "so nothing is spoken instead of a fragment") if low else r.reason_text,
            "untranslated": [] if ai_ok else r.untranslated, "clauses": r.clauses, "intents": r.intents, "rules_status": r.status, "coverage": r.coverage,
            "ai": ({**ai, "name": llm_fallback.NAME} if ai else None),
            "speaks": urls["listener"], "notices": urls["speaker"], "play_s": round(max(play_s.values()), 2),
            "ms": {"stt": round((t1 - t0) * 1000), "rules": round((t2 - t1) * 1000, 2), "tts": round((t3 - tl) * 1000),
                   "total": round((t3 - t0) * 1000), **({"llm": round((tl - t2) * 1000)} if ai else {})},
            "audio_s": round(duration(wav), 2), "audio_level": level(wav),
        }
        if source == "mic" and os.environ.get("SAVE_MIC_AUDIO"):           # for diagnosing a recognition problem; off by default (it keeps a real voice on disk)
            (OUT / "mic").mkdir(parents=True, exist_ok=True)
            (OUT / "mic" / f"turn{n}_{who}.wav").write_bytes(wav)
        with self.lock:
            self.history.append(rec)
        # each window gets only what is meant for it, in its own language
        replayed = bool(ai_ok and ai.get("replayed"))
        self.publish(who, {"type": "you_said", "n": n, "text": heard, "status": rec["status"], "notices": urls["speaker"],
                           "original": original_url, "replayed": replayed})
        if urls["listener"]:
            self.publish(listener, {"type": "incoming", "n": n, "status": rec["status"], "text": " ".join(c["text"] for c in urls["listener"]),
                                    "speaks": urls["listener"], "lang": dst, "replayed": replayed})
        if ai_ok:                                            # an English gloss for the operator panel, after the listener already has the audio
            gloss = self.llm.meaning(heard, src)
            gloss = "" if "[unclear]" in gloss.lower() else gloss          # an English gloss with a gap in it is not shown
            rec["english"] = f"{gloss} (AI gloss, not checked)" if gloss else "(AI translation; no English gloss)"
        self.publish("stage", {"type": "turn", **rec})
        return rec

    def safe_process(self, who, wav, **kw):
        """process() for the scripted call: a failed turn is reported on screen and the call carries on."""
        try:
            return self.process(who, wav, **kw)
        except (gnani.ApiError, OSError) as e:
            self.publish("stage", {"type": "error", "message": f"{who}'s turn failed: {e}"})
            self.publish(who, {"type": "error", "message": "The interpreter could not process this turn. Please say it again."})
            return None

    def latency(self):
        done = [h["ms"]["total"] for h in self.history if h["status"] != "silent"]
        if not done:
            return {}
        s = sorted(done)
        return {"turns": len(s), "median_ms": s[len(s) // 2], "min_ms": s[0], "max_ms": s[-1]}

    # ------------------------------------------------------------------------------------------ the scripted call
    def make_clip(self, step, n, earlier):
        who = step["who"]
        p = self.roles[who]
        tts_lang = p.get("tts", p["lang"])
        key = "|".join((p["voice"], p["lang"], step["text"]))
        cache = OUT / "clips" / f"{zlib.crc32(key.encode()):08x}.wav"
        shared = SHARED_CLIPS / cache.name                  # the saved demo's synthetic voices, so it replays without new Timbre calls
        if cache.exists():
            clean = cache.read_bytes()
        elif shared.exists():
            clean = shared.read_bytes()
        else:
            clean = self.api.tts(step["text"], p["voice"], tts_lang)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(clean)
        if who == "customer":
            return clean, gnani.degrade(clean, 20, seed=seed("live", n))
        babble = [noise.to_8k(c) for c in earlier] or [noise.to_8k(clean)]
        return clean, gnani.pad_if_short(noise.add_noise(clean, "bike", self.biker_snr, babble, seed=seed("live", n)))

    def play_script(self, script=SCRIPT, ring_s=1.6, gap_s=0.9, roles="kn"):
        """Ring, answer, play every turn through the real pipeline, hang up. Blocks; run it on a thread."""
        with self.lock:
            if self.script_running:
                return False
            self.script_running = True
        self.stop_flag.clear()
        try:
            if self.state in ("ringing", "connected"):
                self.end_call()
            self.stop_flag.clear()
            self.start_call(roles)
            self.sleep(ring_s)
            self.answer()
            self.sleep(0.8)
            earlier = []
            for i, step in enumerate(script, 1):
                if self.stop_flag.is_set():
                    break
                try:
                    clean, heard_by_interpreter = self.make_clip(step, i, earlier)
                except (gnani.ApiError, OSError) as e:
                    self.publish("stage", {"type": "error", "message": f"could not synthesise the demo voice for turn {i}: {e}"})
                    continue
                earlier.append(clean)
                url = self.put_audio(heard_by_interpreter)
                self.publish(step["who"], {"type": "speaking", "n": i, "seconds": duration(heard_by_interpreter), "original": url,
                                           "demo_voice": True})
                self.publish("stage", {"type": "speaking", "n": i, "who": step["who"], "text": step["text"]})
                self.sleep(duration(heard_by_interpreter))              # the speaker is talking; the pipeline starts when they stop
                rec = self.safe_process(step["who"], heard_by_interpreter, source="script", original_url=url, said=step["text"])
                self.sleep((rec["play_s"] if rec else 0) + gap_s)
            self.sleep(0.6)
        finally:
            self.script_running = False
            if self.state != "ended":
                self.end_call()
        return True


# ================================================================================================== HTTP
CONTENT = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
           ".svg": "image/svg+xml"}


def make_handler(room):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LiveCall/1"

        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("body too large")
            return self.rfile.read(n)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/stage"):
                return self.static("index.html")
            if u.path == "/phone":
                return self.static("phone.html")
            if u.path.startswith("/audio/"):
                wav = room.audio.get(u.path[len("/audio/"):].removesuffix(".wav"))
                return self.send(200, wav, "audio/wav") if wav else self.send(404, {"error": "no such audio"})
            if u.path == "/api/events":
                return self.events((q.get("role") or ["stage"])[0])
            if u.path == "/api/latency":
                return self.send(200, room.latency())
            if u.path == "/api/status":
                return self.send(200, room.snapshot("stage"))
            return self.static(u.path.lstrip("/"))

        def static(self, name):
            f = (WEB / name).resolve()
            if WEB.resolve() not in f.parents or not f.is_file():
                return self.send(404, {"error": "not found"})
            self.send(200, f.read_bytes(), CONTENT.get(f.suffix, "application/octet-stream"))

        def events(self, role):
            if role not in room.subs:
                return self.send(404, {"error": "unknown role"})
            q = room.subscribe(role)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    try:
                        ev = q.get(timeout=12)
                        self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                room.unsubscribe(role, q)

        def do_POST(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path == "/api/utterance":
                    who = (q.get("who") or [""])[0]
                    rec = room.process(who, self.body(), source="mic")
                    return self.send(200, {k: rec[k] for k in ("n", "heard", "status", "ms", "output", "english")})
                data = json.loads(self.body() or b"{}")
                if u.path == "/api/call":
                    act = data.get("action")
                    ok = {"start": room.start_call, "answer": room.answer, "end": lambda: (room.end_call(), True)[1]}[act]()
                    return self.send(200, {"ok": bool(ok), "state": room.state})
                if u.path == "/api/prefs":
                    room.set_pref(data.get("role"), data.get("hear"))
                    return self.send(200, {"ok": True, "prefs": room.prefs})
                if u.path == "/api/play":
                    if room.script_running:
                        return self.send(409, {"error": "the scripted call is already running"})
                    name = data.get("script", "default")
                    if name not in SCRIPTS:
                        return self.send(400, {"error": f"unknown script {name!r}; choose one of {sorted(SCRIPTS)}"})
                    threading.Thread(target=room.play_script, args=(SCRIPTS[name],), kwargs={"roles": SCRIPT_ROLES[name]}, daemon=True).start()
                    return self.send(200, {"ok": True})
                if u.path == "/api/stop":
                    room.end_call()
                    return self.send(200, {"ok": True})
                return self.send(404, {"error": "not found"})
            except RuntimeError as e:
                return self.send(409, {"error": str(e)})
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                return self.send(400, {"error": str(e)})
            except gnani.ApiError as e:
                return self.send(502, {"error": f"Gnani API error: {e}"})

    return Handler


def run_headless(api, out_dir=None, name="results.json", biker_snr=5, script=SCRIPT, llm=None, roles="kn"):
    """The scripted call with no browser and no waiting: every turn goes through the real pipeline and the numbers are saved.
    Used for the README, so the documented results are a file and not a recollection of a browser session."""
    out = Path(out_dir or OUT)
    out.mkdir(parents=True, exist_ok=True)
    room = CallRoom(api, sleep=lambda s: None, biker_snr=biker_snr, llm=llm)
    live = []
    q = room.subscribe("stage")
    room.play_script(script, roles=roles)
    while not q.empty():
        ev = q.get_nowait()
        if ev["type"] == "error":
            live.append(ev["message"])
    turns = []
    for h in room.history:
        h = dict(h)
        h["speaks"] = [{"text": c["text"], "lang": c["lang"]} for c in h["speaks"]]
        h["notices"] = [{"text": c["text"], "lang": c["lang"]} for c in h["notices"]]
        turns.append(h)
    res = {"people": ROLE_SETS[roles], "interpreter": INTERPRETER, "biker_snr": biker_snr, "turns": turns, "errors": live,
           "latency": room.latency(), "calls": dict(getattr(api, "calls", {})), "ai_fallback": bool(llm)}
    (out / name).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def serve(room, host="127.0.0.1", port=8770):
    srv = ThreadingHTTPServer((host, port), make_handler(room))
    srv.daemon_threads = True
    return srv


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--run", action="store_true", help="run the scripted call once without a browser and save out/live/results.json")
    ap.add_argument("--script", choices=sorted(SCRIPTS), default="default", help="which scripted call to run (real needs the AI fallback for its casual lines; english is a customer who speaks English and a biker who speaks Hindi)")
    ap.add_argument("--replay-ai", nargs="?", const=str(HERE / "demos" / "realistic_call_10db.json"), default=None, metavar="FILE",
                    help="play the AI fallback from the answers recorded in FILE (default: the saved realistic call) instead of a live model")
    ap.add_argument("--biker-snr", type=float, default=5, help="bike noise level in dB for the biker's synthetic voice (default 5)")
    ap.add_argument("--name", default=None, help="result file name for --run (default results.json, or results_bike<N>.json when --biker-snr is changed)")
    args = ap.parse_args()
    def make_llm():
        if args.replay_ai:
            guard_on = (os.environ.get("LLM_GUARD") or llm_fallback._dotenv("LLM_GUARD") or "on").strip().lower() not in ("off", "0", "no", "false")
            return llm_fallback.ReplayLlm(args.replay_ai, guard_on=guard_on)
        return llm_fallback.LlmFallback.from_env()

    ok, why = gnani.check_network()
    if not ok:
        print(f"WARNING: cannot reach api.vachana.ai ({why}). A call needs the network.")
        if args.run:
            raise SystemExit(1)
    if args.run:
        name = args.name or ("results.json" if args.biker_snr == 5 else f"results_bike{args.biker_snr:g}.json")
        if args.script != "default" and not args.name:
            name = f"results_{args.script}.json"
        res = run_headless(GnaniApi(), name=name, biker_snr=args.biker_snr, llm=make_llm(), script=SCRIPTS[args.script], roles=SCRIPT_ROLES[args.script])
        for t in res["turns"]:
            print(f"turn {t['n']} {t['who']:<8} {t['status']:<12} heard {t['heard']!r} -> {t['output'] or '(refused)'!r}   "
                  f"stt {t['ms']['stt']} ms, tts {t['ms']['tts']} ms, ready after {t['ms']['total']} ms")
        print(f"\nlatency {res['latency']}   API calls {res['calls']}   errors {res['errors'] or 'none'}\nsaved {OUT / name}")
        return
    llm = make_llm()
    srv = serve(CallRoom(GnaniApi(), biker_snr=args.biker_snr, llm=llm), port=args.port)
    print(f"AI fallback: {'ON, using ' + llm.host + (' -- REPLAY: only the sentences of the recorded call can be answered' if getattr(llm, 'replay', False) else '') + (' (the rules go first; the AI answer is checked against what was said)' if getattr(llm, 'guard_on', True) else ' (the rules go first; the CHECK IS OFF: AI answers are spoken unchecked)') if llm else 'off (set LLM_BASE_URL to turn it on)'}")
    print(f"Live call interpreter: http://127.0.0.1:{args.port}/   (Ctrl+C to stop)\n"
          f"  separate windows: /phone?role=customer  and  /phone?role=biker")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
