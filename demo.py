"""End-to-end demo for the 60-second video. Everything is synthetic.

Scene 1  customers describe one house (Hindi and Marathi voices, phone-line audio) -> Prisma -> store
Scene 2  a Marathi rider on a bike hears the merged route (Timbre), repeats each landmark through bike
         noise, and the checkpoint flow decides: accept / read-back / ask again / tap fallback
Scene 3  noise ladder: the same landmark at 10, 5, 0 dB bike noise and 5 dB babble (real results)
Outputs  out/demo/: every audio clip, demo_log.md, storyboard.md, demo_sequence.wav, demo.db

Run:  python demo.py            (uses a response cache in out/demo/cache; --fresh ignores it)
Outcomes are whatever Prisma returns with fixed noise seeds. Nothing is re-rolled to look better.
"""
import argparse
import csv
import hashlib
import json
import sys
import time
import zlib
from collections import Counter
from pathlib import Path

import gnani
import noise
from checkpoint import PROMPTS, Checkpoint
from extraction import CRITICAL
from phrases import render
from store import LandmarkStore
from verify import ASK_AGAIN, CONFIRM, verify

P, C, H = "411001", "kothrud", "house-7"
CUSTOMERS = [
    dict(id="c1", lang="hi-IN", voice="Nalini", text="मंदिर के पीछे, फिर नीला गेट, फिर हरा मकान"),
    dict(id="c2", lang="mr-IN", voice="Zahira", text="देवळाच्या मागे, मग निळे गेट"),
    dict(id="c3", lang="hi-IN", voice="Deepak", text="नीला गेट, फिर हरा मकान"),
    dict(id="c4", lang="hi-IN", voice="Nalini", text="मंदिर के पीछे, फिर लाल गेट"),   # the one who disagrees
]
BOT_VOICE = {"mr-IN": "Zahira", "hi-IN": "Nalini"}
RIDER_VOICE = {"mr-IN": "Ishaan", "hi-IN": "Deepak"}
CARRIER = {"mr-IN": "मला {p} दिसले", "hi-IN": "मुझे {p} दिख रहा है"}   # about 1 s of speech is too short for Prisma
YES_SAY = {"mr-IN": "हो, बरोबर आहे", "hi-IN": "हाँ, सही है"}
RIDER_SNRS = [10, 5, 0]
LADDER = [("bike@10", "bike", 10), ("bike@5", "bike", 5), ("bike@0", "bike", 0), ("babble@5", "babble", 5)]
LANG_NAME = {"mr-IN": "Marathi", "hi-IN": "Hindi"}
REPLAY_LABEL = "REPLAYED FROM THE SWEEP, NOT FROM THIS RUN"
DEFAULT_SWEEP_CSV = gnani.HERE / "out" / "hard_results.csv"


def seed(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode()) % 100_000


# ---------------------------------------------------------------- API layer
class LiveApi:
    """Real Timbre / Prisma calls with an on-disk cache (so re-runs cost no credits)."""

    def __init__(self, cache_dir, use_cache=True):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.stt_path = self.dir / "stt.json"
        self.stt_cache = json.loads(self.stt_path.read_text()) if self.stt_path.exists() else {}
        self.calls = {"tts": 0, "stt": 0}

    def tts(self, text, voice, lang, hint=None):
        f = self.dir / (hashlib.sha1(f"{text}|{voice}|{lang}".encode()).hexdigest() + ".wav")
        if self.use_cache and f.exists():
            return f.read_bytes()
        wav = gnani.tts(text, voice, lang)
        self.calls["tts"] += 1
        f.write_bytes(wav)
        time.sleep(0.2)
        return wav

    def stt(self, audio, lang, hint=None, ctx=None):
        key = hashlib.sha1(audio + lang.encode()).hexdigest()
        if self.use_cache and key in self.stt_cache:
            return self.stt_cache[key]
        text = gnani.stt(audio, lang)
        self.calls["stt"] += 1
        self.stt_cache[key] = text
        self.stt_path.write_text(json.dumps(self.stt_cache, ensure_ascii=False))
        time.sleep(0.2)
        return text


# ---------------------------------------------------------------- audio helpers
def resample(samples, sr_in, sr_out):
    if sr_in == sr_out:
        return list(samples)
    n = int(len(samples) * sr_out / sr_in)
    out = []
    for i in range(n):
        pos = i * sr_in / sr_out
        j = int(pos)
        a, b = samples[j], samples[min(j + 1, len(samples) - 1)]
        out.append(int(a + (b - a) * (pos - j)))
    return out


def join_wavs(items, gap=0.45, sr=16000):
    out = []
    for _label, wav in items:
        s, r = gnani.read_wav(wav)
        out += resample(s, r, sr) + [0] * int(gap * sr)
    return gnani.write_wav(out, sr)


# ---------------------------------------------------------------- replay of recorded sweep transcripts
def load_replay_cases(csv_path):
    """Read the 24-phrase sweep and verify every recorded transcript against the phrase that was spoken.

    Selection rule, fixed in advance: the first CONFIRM row and the first ASK_AGAIN row in file order.
    Counts cover every row so nothing is hidden.
    """
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("part") == "hard"]
    counts, first = Counter(), {}
    for i, r in enumerate(rows):
        v = verify(r["ref"], r["hyp"])
        counts[v.decision] += 1
        if v.decision in (CONFIRM, ASK_AGAIN) and v.decision not in first:
            first[v.decision] = dict(row=r, line=i + 2, reason=v.reason)     # +2: header row, 1-based
    return rows, counts, [first[k] for k in (CONFIRM, ASK_AGAIN) if k in first]


def replay_scene(api, csv_path, save, seq):
    """Run recorded Prisma transcripts through the checkpoint flow. Prisma is not called; only Timbre speaks the
    bot's prompts. The rider's first utterance is a real recorded transcript; a yes reply is scripted."""
    out = dict(label=REPLAY_LABEL, source=str(csv_path), cases=[], counts={}, total=0)
    if not Path(csv_path).exists():
        out["error"] = f"sweep results not found: {csv_path}"
        return out
    rows, counts, picks = load_replay_cases(csv_path)
    out["total"], out["counts"] = len(rows), {k: counts.get(k, 0) for k in ("ACCEPT", "CONFIRM", "ASK_AGAIN", "MISMATCH")}
    for k, pick in enumerate(picks, 1):
        r, lang = pick["row"], pick["row"]["lang"]
        bot = BOT_VOICE[lang]
        cp = Checkpoint(r["ref"], lang)
        case = dict(n=k, lang=lang, group=r["group"], condition=r["cond"], sweep_csv_line=pick["line"],
                    expected=r["ref"], steps=[])

        def say(text, tag):
            w = api.tts(text, bot, lang, hint=text)
            name = save(f"5_replay_case{k}_bot_{tag}.wav", w)
            seq.append((f"replay case {k}: bot {tag}", w))
            return name

        action = cp.hear(r["hyp"])
        case["steps"].append(dict(source="recorded Prisma transcript", text=r["hyp"], action=action.kind,
                                  reason=action.reason, bot_says=action.text))
        case["steps"][-1]["prompt_audio"] = say(action.text, action.kind.lower()) if action.text else None
        if action.kind == "CONFIRM_YN":
            reply = YES_SAY[lang]
            action = cp.hear(reply)
            case["steps"].append(dict(source="scripted reply, not recorded", text=reply, action=action.kind,
                                      reason=action.reason, bot_says=action.text))
            case["steps"][-1]["prompt_audio"] = say(PROMPTS[lang]["done"], "done")
        case["status"] = cp.status or "UNRESOLVED"
        if case["status"] == "UNRESOLVED":
            case["note"] = ("Replay stops at the bot's question: the sweep recorded one transcript per clip, "
                            "so there is no real second attempt to replay.")
        out["cases"].append(case)
    return out


# ---------------------------------------------------------------- the demo
def run(api, out_dir, rider_lang="mr-IN", clock=time.time, customers=CUSTOMERS, stress=False,
        replay=False, sweep_csv=DEFAULT_SWEEP_CSV):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "demo.db"
    if db.exists():
        db.unlink()
    for f in list(out.glob("[1-5]_*.wav")) + [out / "demo_sequence.wav", out / "replay_sequence.wav"]:
        if f.exists():
            f.unlink()
    store = LandmarkStore(str(db))
    rseq = []                                # replay audio is kept apart from this run's audio
    seq, clips = [], []                      # seq: (label, wav) for the video audio; clips: babble sources
    res = {"customers": [], "route_before": [], "steps": [], "ladder": [], "rider_lang": rider_lang}

    def save(name, wav):
        (out / name).write_bytes(wav)
        return name

    # ---- Scene 1: customers
    for c in customers:
        clean = api.tts(c["text"], c["voice"], c["lang"], hint=c["text"])
        line = gnani.degrade(clean, 20, seed=seed(c["id"]))          # phone line, light noise
        heard = api.stt(line, c["lang"], hint=c["text"], ctx={"snr": 20})
        keys = store.add_description(P, C, H, c["id"], heard, c["lang"], clock())
        audio = save(f"1_customer_{c['id']}_{c['lang']}.wav", line)
        seq.append((f"customer {c['id']}", line))
        clips.append(noise.to_8k(clean))
        res["customers"].append(dict(id=c["id"], lang=c["lang"], voice=c["voice"], said=c["text"], heard=heard,
                                     landmarks=len(keys), audio=audio))
    route = store.route(P, C, H, clock())
    res["route_before"] = [dict(text=r.text, support=r.support, confidence=r.confidence, state=r.state,
                                contested=r.contested, alternatives=len(r.alternatives)) for r in route]
    if not route:
        res["error"] = "no route could be built from the transcripts"
        return finish(res, out, store, seq, api)

    # ---- rider flow: used by scene 2 and by the optional stress scene
    bot = BOT_VOICE[rider_lang]
    rider = RIDER_VOICE[rider_lang]

    def ride(step, label, kind, snr, seed_fn, prefix, simulate_tap=True):
        phrase = render(step.slots, rider_lang) or step.text
        cp = Checkpoint(phrase, rider_lang)
        entry = dict(label=label, phrase=phrase, kind=kind, snr=snr, attempts=[], seeds=[],
                     rendered=render(step.slots, rider_lang) is not None)
        nxt = cp.prompt_next().text
        w = api.tts(nxt, bot, rider_lang, hint=nxt)
        entry["next_text"], entry["next_audio"] = nxt, save(f"{prefix}_a_bot_next.wav", w)
        seq.append((f"bot: next landmark ({label})", w))
        spoken = CARRIER[rider_lang].format(p=phrase)
        base = api.tts(spoken, rider, rider_lang, hint=spoken)

        n = 0
        while cp.state not in ("DONE", "AWAIT_TAP") and n < 6:
            n += 1
            if cp.state == "AWAIT_YN":
                said = YES_SAY[rider_lang]
                clean = api.tts(said, rider, rider_lang, hint=said)
            else:
                said, clean = spoken, base
            sd = seed_fn(n)
            entry["seeds"].append(sd)
            noisy = gnani.pad_if_short(noise.add_noise(clean, kind, snr, clips, seed=sd))
            heard = api.stt(noisy, rider_lang, hint=said,
                            ctx={"snr": snr, "kind": kind, "attempt": n, "state": cp.state})
            action = cp.hear(heard)
            rider_audio = save(f"{prefix}_b_rider_try{n}_{kind}{snr}dB.wav", noisy)
            seq.append((f"rider {label} try {n} ({kind} {snr} dB)", noisy))
            entry["attempts"].append(dict(n=n, said=said, heard=heard, state_after=cp.state, action=action.kind,
                                          reason=action.reason, prompt=action.text, audio=rider_audio, prompt_audio=None))
            if action.text and cp.state != "DONE":
                pw = api.tts(action.text, bot, rider_lang, hint=action.text)
                entry["attempts"][-1]["prompt_audio"] = save(f"{prefix}_c_bot_{action.kind.lower()}_{n}.wav", pw)
                seq.append((f"bot: {action.kind}", pw))
        if cp.state == "AWAIT_TAP":
            entry["tap_fallback"] = True
            if simulate_tap:
                cp.tap(True)                               # simulated rider button press
        if cp.state == "DONE":
            done = api.tts(PROMPTS[rider_lang]["done"], bot, rider_lang, hint=PROMPTS[rider_lang]["done"])
            entry["done_text"], entry["done_audio"] = PROMPTS[rider_lang]["done"], save(f"{prefix}_d_bot_done.wav", done)
            seq.append(("bot: done", done))
        entry.update(status=cp.status or "AWAITING_TAP", method=cp.method)
        return cp, entry

    # ---- Scene 2: rider
    for idx, step in enumerate(route):
        snr = RIDER_SNRS[idx % len(RIDER_SNRS)]
        cp, entry = ride(step, f"step {idx + 1}", "bike", snr,
                         lambda n, idx=idx, snr=snr: seed(idx, n, snr), f"2_step{idx + 1}")
        entry["step"] = idx + 1
        store.record_checkpoint(step.landmark_id, cp, f"demo-{idx}", clock())
        res["steps"].append(entry)

    # ---- Scene 3: noise ladder on the first step that has a colour word
    ladder_step = next((r for r in route if r.slots.get("colour")), route[0])
    lphrase = render(ladder_step.slots, rider_lang) or ladder_step.text
    lspoken = CARRIER[rider_lang].format(p=lphrase)
    lbase = api.tts(lspoken, rider, rider_lang, hint=lspoken)
    for name, kind, snr in LADDER:
        noisy = noise.add_noise(lbase, kind, snr, clips, seed=seed("ladder", name))
        noisy = gnani.pad_if_short(noisy)
        heard = api.stt(noisy, rider_lang, hint=lspoken, ctx={"snr": snr, "kind": kind, "ladder": True})
        v = verify(lphrase, heard)
        audio = save(f"3_ladder_{name.replace('@', '_')}.wav", noisy)
        res["ladder"].append(dict(cond=name, kind=kind, snr=snr, heard=heard, decision=v.decision, reason=v.reason,
                                  audio=audio))
    res["ladder_phrase"], res["ladder_said"] = lphrase, lspoken

    # ---- Scene 4 (optional): stress. One rider step, babble at 5 dB, fixed seeds, run once, not re-rolled.
    # The step is chosen by a rule fixed in advance, not by looking at results: the landmark with the most
    # critical words, because a read-back can only happen when some words match and others do not.
    if stress:
        def n_critical(r):
            return sum(1 for k in CRITICAL if r.slots.get(k))
        _, sstep = max(enumerate(route), key=lambda t: (n_critical(t[1]), -t[0]))
        _, entry = ride(sstep, "stress", "babble", 5,
                        lambda n: seed("stress", n, "babble", 5), "4_stress", simulate_tap=False)
        entry["recorded_in_store"] = False
        res["stress"] = entry

    # ---- Scene 5 (optional): replay of recorded sweep transcripts. Not from this run; kept in its own files.
    if replay:
        res["replay"] = replay_scene(api, sweep_csv, save, rseq)

    res["route_after"] = [dict(text=r.text, support=r.support, confidence=r.confidence, state=r.state,
                               contested=r.contested) for r in store.route(P, C, H, clock())]
    return finish(res, out, store, seq, api, rseq)


def finish(res, out, store, seq, api, rseq=None):
    if seq:
        (out / "demo_sequence.wav").write_bytes(join_wavs(seq))
    if rseq:
        (out / "replay_sequence.wav").write_bytes(join_wavs(rseq))
    res["calls"] = dict(getattr(api, "calls", {}))
    (out / "demo_log.md").write_text(render_log(res), encoding="utf-8")
    (out / "storyboard.md").write_text(render_storyboard(res), encoding="utf-8")
    (out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    store.db.close()
    return res


# ---------------------------------------------------------------- reports
def render_log(res):
    L = ["# Demo log (synthetic data; real Prisma and Timbre outputs)", ""]
    L += ["## Scene 1: customers", "", "| customer | language | said | Prisma heard |", "|---|---|---|---|"]
    for c in res["customers"]:
        L.append(f"| {c['id']} | {c['lang']} | {c['said']} | {c['heard']} |")
    L += ["", "## Route after merging", "", "| step | support | confidence | state | contested |", "|---|---|---|---|---|"]
    for r in res["route_before"]:
        L.append(f"| {r['text']} | {r['support']} | {r['confidence']} | {r['state']} | {r['contested']} |")
    L += ["", f"## Scene 2: rider ({LANG_NAME[res['rider_lang']]}, bike noise)", ""]
    for s in res["steps"]:
        L.append(f"### Step {s['step']}: {s['phrase']}  ({s['kind']} {s['snr']} dB)" + ("" if s["rendered"] else "  [customer wording, not rendered]"))
        for a in s["attempts"]:
            L.append(f"- try {a['n']}: said `{a['said']}` -> heard `{a['heard']}` -> **{a['action']}** ({a['reason']})")
        L.append(f"- result: {s['status']} by {s['method']}" + (" (tap fallback)" if s.get("tap_fallback") else ""))
        L.append("")
    L += ["## Scene 3: noise ladder", "", f"Landmark: {res.get('ladder_phrase', '')}", "",
          "| condition | Prisma heard | decision |", "|---|---|---|"]
    for r in res["ladder"]:
        L.append(f"| {r['cond']} | {r['heard']} | {r['decision']} ({r['reason']}) |")
    if "stress" in res:
        st = res["stress"]
        L += ["", f"## Scene 4: stress ({st['kind']} at {st['snr']} dB, one run, seeds {st['seeds']})", "",
              f"Landmark: {st['phrase']}. Chosen before running: the landmark with the most critical words. "
              "Not re-rolled, and not added to the store.", ""]
        for a in st["attempts"]:
            L.append(f"- try {a['n']}: said `{a['said']}` -> heard `{a['heard']}` -> **{a['action']}** ({a['reason']})"
                     + (f"; bot says: {a['prompt']}" if a["prompt"] else ""))
        L.append(f"- result: {st['status']}" + (f" by {st['method']}" if st["method"] else "")
                 + (" (rider's button press NOT simulated)" if st.get("tap_fallback") else ""))
    if "replay" in res:
        rp = res["replay"]
        L += ["", f"## Scene 5: {rp['label']}", "",
              f"**{rp['label']}.** These are recorded Prisma transcripts from `{rp['source']}`, the 24-phrase noise sweep "
              "(synthetic voices, simulated noise). Prisma was not called for them. Only the bot's prompts are new Timbre audio. "
              "The sweep did not save the audio of its clips, so show the transcript on screen while the prompt plays.", ""]
        if "error" in rp:
            L.append(f"Not run: {rp['error']}")
        else:
            c = rp["counts"]
            L += [f"Rule fixed in advance: the first read-back row and the first ask-again row in file order. "
                  f"All {rp['total']} recorded transcripts, verified against the phrase that was spoken: "
                  f"accept {c['ACCEPT']}, read-back {c['CONFIRM']}, ask-again {c['ASK_AGAIN']}, mismatch {c['MISMATCH']}.", ""]
            for case in rp["cases"]:
                L.append(f"### Replay case {case['n']} ({case['lang']}, {case['group']}, sweep condition {case['condition']}, "
                         f"csv line {case['sweep_csv_line']}): expected `{case['expected']}`")
                for st in case["steps"]:
                    L.append(f"- [{st['source']}] `{st['text']}` -> **{st['action']}** ({st['reason']})"
                             + (f"; bot says: {st['bot_says']}" if st["bot_says"] else ""))
                L.append(f"- result: {case['status']}" + (f". {case['note']}" if case.get("note") else ""))
                L.append("")
    L += ["", "## Route confidence after rider results", "", "| step | support | confidence | state |", "|---|---|---|---|"]
    for r in res.get("route_after", []):
        L.append(f"| {r['text']} | {r['support']} | {r['confidence']} | {r['state']} |")
    L += ["", "The rider's button press in the tap fallback is simulated (always 'found').", f"API calls this run (cache hits are free): {res.get('calls')}"]
    return "\n".join(L) + "\n"


def render_storyboard(res):
    steps, ladder = res["steps"], res["ladder"]
    readbacks = sum(1 for s in steps for a in s["attempts"] if a["action"] == "CONFIRM_YN")
    ladder_line = ", ".join(f"{r['cond']}: {r['decision']}" for r in ladder)
    rp = res.get("replay")
    replay_line = ("If you use the replay cases, caption them: \"Replayed from an earlier test run, not recorded in this video.\"\n"
                   if rp and rp.get("cases") else "")
    st = res.get("stress")
    stress_line = (f"Stress scene ({st['phrase']}, {st['kind']} {st['snr']} dB, one run): "
                   f"{' -> '.join(a['action'] for a in st['attempts'])} -> {st['status']}\n") if st else ""
    route = " -> ".join(r["text"] for r in res["route_before"])
    return f"""# 60-second storyboard: Landmark Chain

Real results from this run (fixed noise seeds, nothing re-rolled).
Merged route: {route}
Rider checkpoints: {len(steps)}, read-backs triggered: {readbacks}
Noise ladder ({res.get('ladder_phrase', '')}): {ladder_line}
{stress_line}
| time | picture | audio / voice-over |
|---|---|---|
| 0-6 s | Failed-delivery notice, vague address "temple ke peeche, neela gate" | "In India an address is often a landmark. Delivery fails when the rider can't find it." |
| 6-20 s | Four customer voices (Hindi and Marathi) with Prisma transcripts, merging into one route card | customer clips from demo_sequence.wav. "Customers describe the house in their own language. Prisma hears them, and the landmarks merge." |
| 20-40 s | Rider on a bike, route card, waveform with noise. Show one read-back | bot prompt + rider clips. "The rider hears the route in Marathi and repeats each landmark. If the line is unclear, the bot reads it back." |
| 40-52 s | The noise ladder table above, real numbers | "Same landmark at 10, 5 and 0 dB of bike noise and babble. When Prisma is unsure the bot asks again, it never guesses." |
| 52-60 s | Route confidence after the rider's confirmations; end card | "Every delivery makes the route more trustworthy. Built on Gnani Prisma and Timbre." |

On-screen caption, always visible: "Synthetic voices and simulated bike noise. No real customer data."
{replay_line}

## Post draft (edit before posting)
Delivery fails when the address is "behind the temple, blue gate". I built Landmark Chain: customers describe a house in Hindi or Marathi, Prisma hears them, Timbre reads the route back to the rider in his language, and a read-back catches unclear audio. Built with Gnani AI's Prisma and Timbre. All audio is synthetic; noise is simulated.
[Tag Gnani AI's official account] #GnaniAI #GreatIndianAIInternshipChallenge
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="ignore the cache and call the APIs again")
    ap.add_argument("--rider", default="mr-IN", choices=["mr-IN", "hi-IN"])
    ap.add_argument("--replay", action="store_true", help="add the labelled replay of recorded sweep transcripts")
    ap.add_argument("--sweep-csv", default=str(DEFAULT_SWEEP_CSV))
    ap.add_argument("--stress", action="store_true", help="add the optional babble-at-5-dB stress scene")
    ap.add_argument("--out", default=str(gnani.HERE / "out" / "demo"))
    a = ap.parse_args()
    ok, msg = gnani.check_network()
    if not ok:
        sys.exit(f"Cannot reach api.vachana.ai ({msg}). Check your internet connection and run again; "
                 "responses already cached in out/demo/cache are reused.")
    api = LiveApi(Path(a.out) / "cache", use_cache=not a.fresh)
    try:
        res = run(api, a.out, a.rider, stress=a.stress, replay=a.replay, sweep_csv=a.sweep_csv)
    except (gnani.ApiError, OSError) as e:
        sys.exit(f"API error: {e}\nEvery call that succeeded is cached in {a.out}/cache; run the same command again to resume.")
    print(f"\nRoute: {' -> '.join(r['text'] for r in res['route_before'])}")
    for s in res["steps"]:
        print(f"step {s['step']} ({s['snr']} dB): {[x['action'] for x in s['attempts']]} -> {s['status']}")
    print("ladder:", {r["cond"]: r["decision"] for r in res["ladder"]})
    if "stress" in res:
        st = res["stress"]
        print(f"stress ({st['phrase']}, {st['kind']} {st['snr']} dB): {[x['action'] for x in st['attempts']]} -> {st['status']}")
    if "replay" in res:
        rp = res["replay"]
        print(f"[{rp['label']}]", rp.get("error") or {c["n"]: [x["action"] for x in c["steps"]] for c in rp["cases"]})
    print(f"open the page: python build_page.py   (writes {a.out}/index.html)")
    print(f"live API calls: {res['calls']}   files in {a.out}")


if __name__ == "__main__":
    main()
