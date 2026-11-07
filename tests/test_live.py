import base64
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gnani  # noqa: E402
import live_call  # noqa: E402
from live_call import CallRoom  # noqa: E402

SENTENCE = "भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ"
WAV = gnani.write_wav([300] * 16000, 16000)


class FakeLive:
    """Prisma returns the next scripted transcript; Timbre returns a half-second clip and remembers what it was asked to say."""

    def __init__(self, transcripts=()):
        self.transcripts = list(transcripts)
        self.said = []

    def stt(self, wav, lang):
        return self.transcripts.pop(0) if self.transcripts else ""

    def tts(self, text, voice, lang):
        self.said.append((text, voice, lang))
        return gnani.write_wav([200] * 8000, 16000)


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def connected(transcripts, **kw):
    room = CallRoom(FakeLive(transcripts), sleep=lambda s: None, **kw)
    room.start_call()
    room.answer()
    return room


class TestRelay(unittest.TestCase):
    def test_each_window_gets_only_its_own_language(self):
        room = connected([SENTENCE])
        cust, bike, stage = (room.subscribe(r) for r in ("customer", "biker", "stage"))
        for q in (cust, bike, stage):
            drain(q)
        rec = room.process("customer", WAV)
        c, b, s = drain(cust), drain(bike), drain(stage)
        self.assertEqual([e["type"] for e in c], ["you_said"])                 # the customer sees only their own words
        self.assertEqual(c[0]["text"], SENTENCE)
        self.assertEqual([e["type"] for e in b], ["incoming"])                 # the biker gets only the translation
        self.assertEqual(b[0]["lang"], "kn-IN")
        self.assertIn("ನೇರವಾಗಿ ಬನ್ನಿ", b[0]["text"])
        self.assertNotIn("भैया", json.dumps(b, ensure_ascii=False))             # the original Hindi never reaches the biker's window
        self.assertEqual([e["type"] for e in s], ["turn"])
        self.assertEqual(rec["status"], "translated")

    def test_the_translation_is_spoken_by_the_interpreter_in_the_listeners_language(self):
        room = connected([SENTENCE])
        room.process("customer", WAV)
        text, voice, lang = room.api.said[0]
        self.assertEqual((voice, lang), ("Saanvi", "kn-IN"))
        self.assertIn("ಬರುತ್ತಿದ್ದೇನೆ", text)

    def test_the_reply_goes_back_in_hindi(self):
        room = connected(["ಕಟ್ಟಡ ಕಾಣಿಸಿತು"])
        cust = room.subscribe("customer"); drain(cust)
        room.process("biker", WAV)
        e = drain(cust)[0]
        self.assertEqual((e["type"], e["lang"], e["text"]), ("incoming", "hi-IN", "बिल्डिंग दिख गई"))
        self.assertEqual(room.api.said[0][1:], ("Nalini", "hi-IN"))

    def test_english_is_a_per_person_choice_and_changes_the_spoken_language(self):
        room = connected([SENTENCE])
        room.set_pref("biker", "en")
        bike = room.subscribe("biker"); drain(bike)
        rec = room.process("customer", WAV)
        e = drain(bike)[0]
        self.assertEqual(e["lang"], "en")
        self.assertEqual(e["text"], "come straight, turn right, you will see a building ahead, wait there, I am coming")
        self.assertEqual(room.api.said[0][2], "en-IN")
        self.assertEqual(rec["dst"], "en")
        self.assertEqual(room.prefs["customer"], "native")                      # the other person's choice is untouched

    def test_a_partial_translation_speaks_the_translation_and_then_a_notice(self):
        room = connected(["भैया मैं पांच मिनट में आ रहा हूँ"])
        bike = room.subscribe("biker"); drain(bike)
        rec = room.process("customer", WAV)
        self.assertEqual(rec["status"], "partial")
        self.assertEqual(len(rec["speaks"]), 2)
        self.assertEqual(rec["untranslated"], ["पांच", "मिनट"])
        self.assertEqual(rec["notices"], [])                                    # the speaker is not interrupted for a partial
        self.assertEqual(len(drain(bike)[0]["speaks"]), 2)

    def test_a_refusal_tells_both_people_in_their_own_language(self):
        room = connected(["भैया चाय पीकर आना"])
        cust, bike = room.subscribe("customer"), room.subscribe("biker")
        drain(cust); drain(bike)
        rec = room.process("customer", WAV)
        self.assertEqual(rec["status"], "untranslated")
        c, b = drain(cust)[0], drain(bike)[0]
        self.assertEqual(len(c["notices"]), 1)                                  # to the speaker, in Hindi
        self.assertEqual(c["notices"][0]["lang"], "hi-IN")
        self.assertEqual(b["speaks"][0]["lang"], "kn-IN")                       # to the listener, in Kannada
        self.assertNotIn("चाय", json.dumps(b, ensure_ascii=False))

    def test_the_speakers_own_notice_follows_the_language_they_chose_to_hear(self):
        room = connected(["भैया चाय पीकर आना", "भैया चाय पीकर आना"])
        room.set_pref("customer", "en")
        rec = room.process("customer", WAV)
        self.assertEqual(rec["notices"][0]["lang"], "en")
        self.assertTrue(rec["notices"][0]["text"].isascii())
        room.set_pref("customer", "native")
        self.assertEqual(room.process("customer", WAV)["notices"][0]["lang"], "hi-IN")

    def test_every_turn_records_how_loud_the_recording_was(self):
        room = connected([SENTENCE])
        quiet = gnani.write_wav([int(300 * ((i % 40) - 20) / 20) for i in range(16000)], 16000)
        rec = room.process("customer", quiet)
        self.assertLess(rec["audio_level"]["peak_pct"], 2)
        self.assertEqual(rec["audio_level"]["clipped_pct"], 0)
        loud = live_call.level(gnani.write_wav([32767, -32768] * 2000, 16000))
        self.assertGreater(loud["clipped_pct"], 90)
        self.assertEqual(live_call.level(gnani.write_wav([], 16000))["rms_dbfs"], -99.0)

    def test_a_real_voice_is_only_saved_when_asked_for(self):
        out = Path(tempfile.mkdtemp())
        old = live_call.OUT
        live_call.OUT = out
        try:
            room = connected([SENTENCE, SENTENCE])
            room.process("customer", WAV, source="mic")
            self.assertFalse((out / "mic").exists())
            with mock.patch.dict(os.environ, {"SAVE_MIC_AUDIO": "1"}):
                room.process("customer", WAV, source="mic")
            self.assertEqual(len(list((out / "mic").glob("*.wav"))), 1)
            with mock.patch.dict(os.environ, {"SAVE_MIC_AUDIO": "1"}):
                room.process("customer", WAV, source="script")                    # synthetic voices are never saved this way
            self.assertEqual(len(list((out / "mic").glob("*.wav"))), 1)
        finally:
            live_call.OUT = old

    def test_silence_disturbs_nobody_but_the_speaker(self):
        room = connected([""])
        bike = room.subscribe("biker"); drain(bike)
        rec = room.process("customer", WAV)
        self.assertEqual(rec["status"], "silent")
        self.assertEqual(drain(bike), [])
        self.assertEqual(len(rec["notices"]), 1)

    def test_a_turn_is_refused_when_the_call_is_not_connected(self):
        room = CallRoom(FakeLive([SENTENCE]))
        with self.assertRaises(RuntimeError):
            room.process("customer", WAV)
        room.start_call()
        with self.assertRaises(RuntimeError):
            room.process("customer", WAV)                                       # still ringing

    def test_timings_are_recorded_for_every_stage(self):
        ticks = iter([0.0, 0.2, 0.2, 0.8, 0.8, 0.8, 0.8, 0.8])
        room = CallRoom(FakeLive([SENTENCE]), clock=lambda: next(ticks), sleep=lambda s: None)
        room.start_call(); room.answer()
        rec = room.process("customer", WAV)
        self.assertEqual(rec["ms"]["stt"], 200)
        self.assertEqual(rec["ms"]["tts"], 600)
        self.assertEqual(rec["ms"]["total"], 800)
        self.assertEqual(room.latency()["median_ms"], 800)

    def test_unknown_people_and_choices_are_rejected(self):
        room = connected([SENTENCE])
        with self.assertRaises(ValueError):
            room.process("stranger", WAV)
        with self.assertRaises(ValueError):
            room.set_pref("biker", "tamil")

    def test_a_reconnecting_window_gets_the_current_state(self):
        room = connected([SENTENCE])
        room.process("customer", WAV)
        snap = room.subscribe("stage").get_nowait()
        self.assertEqual((snap["type"], snap["state"]), ("snapshot", "connected"))
        self.assertEqual(len(snap["history"]), 1)
        self.assertEqual(room.subscribe("biker").get_nowait()["history"], [])  # a phone window never gets the log


class TestScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old, self.old_shared = live_call.OUT, live_call.SHARED_CLIPS
        live_call.OUT = Path(self.tmp)
        live_call.SHARED_CLIPS = Path(self.tmp) / "no-saved-clips"     # these tests are about synthesising and caching, not about the saved demo

    def tearDown(self):
        live_call.OUT, live_call.SHARED_CLIPS = self.old, self.old_shared

    def test_the_scripted_call_rings_connects_runs_every_turn_and_hangs_up(self):
        said = [s["text"] for s in live_call.SCRIPT]
        room = CallRoom(FakeLive(said), sleep=lambda s: None)                   # Prisma "hears" exactly what each synthetic voice says
        states = []
        q = room.subscribe("stage"); drain(q)
        room.play_script()
        events = drain(q)
        states = [e["state"] for e in events if e["type"] == "call"]
        self.assertEqual(states, ["ringing", "connected", "ended"])
        self.assertEqual(len(room.history), len(live_call.SCRIPT))
        self.assertEqual([h["status"] for h in room.history], ["translated", "translated", "partial", "untranslated"])
        self.assertFalse(room.script_running)

    def test_the_synthetic_speaker_clips_are_cached_but_the_pipeline_is_not(self):
        said = [s["text"] for s in live_call.SCRIPT]
        room = CallRoom(FakeLive(said * 2), sleep=lambda s: None)
        room.play_script()
        first = len(room.api.said)
        room.play_script()
        second = len(room.api.said) - first
        self.assertLess(second, first)                                          # speaker clips came from disk the second time
        self.assertGreater(second, 0)                                           # but every translation was spoken again

    def test_a_failed_turn_is_reported_and_the_call_carries_on(self):
        api = FakeLive([s["text"] for s in live_call.SCRIPT])
        real_tts, calls = api.tts, []

        def flaky(text, voice, lang):
            calls.append(text)
            if len(calls) == 4:                       # clip 1, translation 1, clip 2, translation 2: this one fails
                raise gnani.ApiError("TTS HTTP 429: busy", 429)
            return real_tts(text, voice, lang)
        api.tts = flaky
        room = CallRoom(api, sleep=lambda s: None)
        stage, bike = room.subscribe("stage"), room.subscribe("biker")
        drain(stage); drain(bike)
        room.play_script()
        errors = [e for e in drain(stage) if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("429", errors[0]["message"])
        self.assertEqual(len(room.history), len(live_call.SCRIPT) - 1)          # that turn is missing, the rest ran
        self.assertEqual(room.state, "ended")
        self.assertTrue(any(e["type"] == "error" for e in drain(bike)))         # the speaker is told to say it again

    def test_the_translation_and_its_notice_are_spoken_one_after_the_other(self):
        room = connected(["भैया मैं पांच मिनट में आ रहा हूँ"])
        seen = []
        real = room.api.tts
        room.api.tts = lambda *a: (seen.append(a[0]), real(*a))[1]
        rec = room.process("customer", WAV)
        self.assertEqual(len(seen), 2)
        self.assertEqual([c["text"] for c in rec["speaks"]], seen)              # translation first, then the notice, never in parallel

    def test_the_headless_run_saves_every_turn_and_the_latency(self):
        out = Path(self.tmp) / "run"
        res = live_call.run_headless(FakeLive([s["text"] for s in live_call.SCRIPT]), out_dir=out)
        saved = json.loads((out / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["turns"]), len(live_call.SCRIPT))
        self.assertEqual(saved["latency"], res["latency"])
        self.assertEqual(saved["biker_snr"], 5)
        self.assertNotIn("url", json.dumps(saved))                              # audio addresses are not results

    def test_the_bike_noise_level_is_a_setting_and_changes_the_biker_audio(self):
        a = CallRoom(FakeLive(), sleep=lambda s: None, biker_snr=5)
        b = CallRoom(FakeLive(), sleep=lambda s: None, biker_snr=15)
        step = dict(who="biker", text="ನಾನು ಇಲ್ಲಿ ನಿಂತಿದ್ದೇನೆ")
        earlier = [gnani.write_wav([int(8000 * ((i % 40) - 20) / 20) for i in range(16000)], 16000)]
        self.assertNotEqual(a.make_clip(step, 2, earlier)[1], b.make_clip(step, 2, earlier)[1])

    def test_stop_ends_the_script_between_turns(self):
        room = CallRoom(FakeLive([s["text"] for s in live_call.SCRIPT]), sleep=lambda s: None)
        orig = room.process

        def stop_after_first(*a, **k):
            r = orig(*a, **k)
            room.end_call()
            return r
        room.process = stop_after_first
        room.play_script()
        self.assertEqual(len(room.history), 1)
        self.assertEqual(room.state, "ended")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestBrowserEncoder(unittest.TestCase):
    """The microphone path encodes 16 kHz WAV in the browser. Run the real encodeWav from app.js under node and read its output with Python."""

    def test_the_browser_writes_a_wav_the_server_and_prisma_can_read(self):
        js = (Path(ROOT) / "live" / "app.js").resolve()
        script = (
            "const vm=require('vm'),fs=require('fs');const ctx={addEventListener(){},window:{},Blob,console};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(js))},'utf8'),ctx);"
            "const rate=48000,n=rate,x=new Float32Array(n);for(let i=0;i<n;i++)x[i]=0.5*Math.sin(2*Math.PI*440*i/rate);"
            "const blob=ctx.encodeWav([x.subarray(0,n/2),x.subarray(n/2)],rate,16000);"
            "blob.arrayBuffer().then(b=>process.stdout.write(Buffer.from(b).toString('base64')));")
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        wav = base64.b64decode(out.stdout)
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 16000))
            self.assertAlmostEqual(w.getnframes(), 16000, delta=2)               # one second of audio, resampled 48 kHz -> 16 kHz
        samples, sr = gnani.read_wav(wav)
        self.assertAlmostEqual(max(samples) / 32767, 0.5, delta=0.03)            # the level survives
        self.assertGreater(sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b), 400)    # about 440 upward zero crossings: the tone survives


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestBrowserGain(unittest.TestCase):
    def peak(self, amplitude):
        js = (Path(ROOT) / "live" / "app.js").resolve()
        script = (
            "const vm=require('vm'),fs=require('fs');const ctx={addEventListener(){},window:{},Blob,console};vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(js))},'utf8'),ctx);"
            f"const x=new Float32Array(48000);for(let i=0;i<48000;i++)x[i]={amplitude}*Math.sin(2*Math.PI*300*i/48000);"
            "ctx.encodeWav([x],48000,16000).arrayBuffer().then(b=>process.stdout.write(Buffer.from(b).toString('base64')));")
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        samples, _ = gnani.read_wav(base64.b64decode(out.stdout))
        return max(samples) / 32767

    def test_a_quiet_microphone_is_brought_up_and_a_normal_one_is_left_alone(self):
        self.assertAlmostEqual(self.peak(0.05), 0.4, delta=0.03)          # x8, the most it will add
        self.assertAlmostEqual(self.peak(0.2), 0.6, delta=0.03)           # brought up to 0.6
        self.assertAlmostEqual(self.peak(0.6), 0.6, delta=0.03)           # not changed
        self.assertAlmostEqual(self.peak(0.0005), 0.0005, delta=0.001)     # silence is not amplified into noise


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.room = CallRoom(FakeLive([SENTENCE]), sleep=lambda s: None)
        cls.srv = live_call.serve(cls.room, port=0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def post(self, path, data=None, raw=None):
        body = raw if raw is not None else json.dumps(data or {}).encode()
        req = urllib.request.Request(self.base + path, data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_the_api_runs_a_call_end_to_end(self):
        self.assertEqual(self.post("/api/utterance?who=customer", raw=WAV)[0], 409)         # nobody has called yet
        self.assertEqual(self.post("/api/call", {"action": "start"})[1]["state"], "ringing")
        self.assertEqual(self.post("/api/call", {"action": "answer"})[1]["state"], "connected")
        code, out = self.post("/api/utterance?who=customer", raw=WAV)
        self.assertEqual(code, 200)
        self.assertEqual(out["status"], "translated")
        self.assertEqual(self.post("/api/prefs", {"role": "biker", "hear": "en"})[1]["prefs"]["biker"], "en")
        self.assertEqual(self.post("/api/prefs", {"role": "biker", "hear": "xx"})[0], 400)
        with urllib.request.urlopen(self.base + "/api/latency", timeout=5) as r:
            self.assertEqual(json.loads(r.read())["turns"], 1)
        self.assertEqual(self.post("/api/call", {"action": "end"})[1]["state"], "ended")

    def test_audio_is_served_and_unknown_things_are_404(self):
        self.room.audio["t1"] = WAV
        with urllib.request.urlopen(self.base + "/audio/t1.wav", timeout=5) as r:
            self.assertEqual(r.read()[:4], b"RIFF")
        for path in ("/audio/nope.wav", "/../live_call.py", "/%2e%2e/live_call.py", "/nothing.html"):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(self.base + path, timeout=5)
                self.assertEqual(cm.exception.code, 404)

    def test_the_pages_are_served(self):
        for path in ("/", "/phone?role=biker"):
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                self.assertIn(b"<!doctype html>", r.read()[:200].lower())

    def test_the_api_key_is_never_in_anything_served(self):
        key = gnani.load_key() if hasattr(gnani, "load_key") else None
        if not key:
            self.skipTest("no key configured")
        for f in Path(live_call.WEB).glob("*"):
            self.assertNotIn(key.encode(), f.read_bytes())


if __name__ == "__main__":
    unittest.main()
