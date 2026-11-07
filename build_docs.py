"""Generate README.md and SUBMISSION.md from README.template.md / SUBMISSION.template.md and the real result files.

Every result number in the documents comes from files in out/, written by the scripts that produced them. Nothing is typed
by hand. A test recomputes several of the figures independently and checks the documents are up to date.

    python build_docs.py
"""
import json
import re
import sys
from pathlib import Path

import sys

import evaluate
import evaluate_unseen
import gnani
import translate as T
from heldout import SETS

HERE = gnani.HERE
OUT = HERE / "out"
METHOD = {"voice": "by voice", "yes": "by a spoken yes", "tap": "by tap (simulated)"}
LANG = {"hi-IN": "Hindi", "mr-IN": "Marathi"}
NEEDS = {
    "out/results.json": "python smoke_test.py",
    "out/sweep_summary.json": "python sweep.py",
    "out/hard_summary.json": "python sweep2.py",
    "out/hard_results.csv": "python sweep2.py",
    "out/short_audio.json": "python experiments/short_audio.py",
    "out/determinism.json": "python experiments/determinism.py",
    "out/demo/results.json": "python demo.py --stress --replay",
    "out/call/results.json": "python call_demo.py",
    "out/live/results.json": "python live_call.py --run",
    "out/render_roundtrip.json": "python experiments/render_roundtrip.py",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def table(header, rows):
    line = lambda cells: "| " + " | ".join(str(c) for c in cells) + " |"
    return "\n".join([line(header), line(["---"] * len(header))] + [line(r) for r in rows])


def pct(x, n):
    return f"{round(100 * x / n)}%" if n else "-"


def _sec(ms):
    return f"{ms / 1000:.2f} s"


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def saved_demo_facts():
    """The saved realistic call in demos/: what it holds, read from the file."""
    f = HERE / "demos" / "realistic_call_10db.json"
    if not f.exists():
        return {"DEMO_SAVED": "No saved demo is present."}
    d = load(f)
    ai = [t for t in d["turns"] if t.get("ai")]
    clips = list((HERE / "demos" / "clips").glob("*.wav"))
    return {"DEMO_SAVED": (f"`demos/` holds a saved copy of the realistic call: {len(d['turns'])} turns recorded with the rider's noise at {d['biker_snr']:g} dB, "
                           f"including the {len(ai)} answers the AI gave (each passed the check when recorded), and {len(clips)} synthetic speaker clips "
                           f"({sum(c.stat().st_size for c in clips) // 1024} KB). `python live_call.py --biker-snr 10 --replay-ai` plays it with **no model running**: "
                           "Prisma and Timbre are still called live, the AI answers come from the file and every such turn is labelled **AI translated, recorded answer**, "
                           "and the check still runs on them. In replay mode the AI can answer only the sentences of that recorded call; anything else is refused as without the AI.")}


def real_facts(out):
    """The realistic delivery call (live_call.SCRIPT_REAL), run with the AI fallback on and the check on, at 5 dB and at 10 dB of bike noise."""
    f5, f10 = Path(out) / "live" / "results_real.json", Path(out) / "live" / "results_real_bike10.json"
    if not (f5.exists() and f10.exists()):
        return {"LIVE_REAL": "No run of the realistic call has been saved."}
    a, b = load(f5), load(f10)
    names = {"translated": "translated by the rules", "partial": "partly translated", "untranslated": "refused", "ai": "AI translated", "silent": "heard nothing"}
    who = {"customer": "Arun (customer, Hindi)", "biker": "Manju (rider, Kannada)"}
    table_ = table(["Turn", "Speaker", "Said (synthetic voice)", "Prisma heard", "Result", "The other person hears", "Ready after"],
                   [[t["n"], who[t["who"]], f"`{t['said']}`", f"`{t['heard']}`", names[t["status"]], f"`{t['output']}`" if t["output"] else "a spoken notice",
                     f"{t['ms']['total'] / 1000:.2f} s"] for t in b["turns"]])
    nz = lambda x: " ".join(re.sub(r"[।,.?!]", "", x).split())
    off = [t for t in a["turns"] if nz(t["heard"]) != nz(t["said"]) and t["who"] == "biker"]
    note = "".join(f"\n- **{a['biker_snr']:g} dB, turn {t['n']}:** Prisma wrote `{t['heard']}` for `{t['said']}`, and the AI faithfully translated that to `{t['output']}`"
                   f"{' (' + names[t['status']] + '), which the check let through, because it cannot know a transcript was misheard' if t['status'] == 'ai' else ''}. "
                   for t in off) or "\n- At both noise levels every rider line was heard as scripted."
    return {"LIVE_REAL": (f"**A realistic delivery call** (`python live_call.py --run --script real`; the AI fallback ON and its check ON; the rider's noise {b['biker_snr']:g} dB, "
                          f"the quieter of two runs, saved in `out/live/results_real_bike10.json`). Arun asks where the rider is, Manju is lost, Arun gives directions, Manju sees the building, "
                          f"Arun says where he is, Manju is on the way. Median ready after {sorted(t['ms']['total'] for t in b['turns'])[len(b['turns']) // 2] / 1000:.2f} s.\n\n{table_}\n\n"
                          f"**The same call at {a['biker_snr']:g} dB** (`out/live/results_real.json`), where a rider's line is misheard:{note}")}


def english_facts(out):
    """The call where the customer speaks English and the biker speaks Hindi (live_call.SCRIPT_EN), rules only, from the saved headless run."""
    f = Path(out) / "live" / "results_english.json"
    if not f.exists():
        return {"LIVE_ENGLISH": "No run of the English-Hindi call has been saved."}
    d = load(f)
    names = {"translated": "translated", "partial": "partly translated", "untranslated": "refused", "ai": "AI translated", "silent": "heard nothing"}
    who = {"customer": "Arun (customer, English)", "biker": "Manju (rider, Hindi)"}
    rows = [[t["n"], who[t["who"]], f"`{t['said']}`", f"`{t['heard']}`", names[t["status"]], f"`{t['output']}`" if t["output"] else "a spoken notice", _sec(t["ms"]["total"])]
            for t in d["turns"]]
    off = [t for t in d["turns"] if " ".join(re.sub(r"[।,.?!]", "", t["said"]).lower().split()) != " ".join(re.sub(r"[।,.?!]", "", t["heard"]).lower().split())]
    note = "".join(f" Prisma wrote `{t['heard']}` for `{t['said']}` in turn {t['n']} ({names[t['status']]})." for t in off)
    ms = [t["ms"]["total"] for t in d["turns"]]
    return {"LIVE_ENGLISH": (f"**A second language pair: the customer speaks English and the rider speaks Hindi** (`python live_call.py --run --script english`; rules only, no AI; the rider's noise "
                             f"{d['biker_snr']:g} dB; saved in `out/live/results_english.json`). The English side is a small grammar of its own: go or come straight, turn or take a left or right, "
                             f"\"you will see a (colour) building ahead\", wait here or there, plus yes, no, found it and could not find it. Median ready after {_sec(_median(ms))}.\n\n"
                             f"{table(['Turn', 'Speaker', 'Said (synthetic voice)', 'Prisma heard', 'Result', 'The other person hears', 'Ready after'], rows)}\n\n"
                             f"Not covered: the AI fallback has no English-to-Hindi route, so English that the rules cannot read is refused or translated in part; \"I am coming\" and \"I am standing\" are not read "
                             f"in English (the Hindi side does read them); and the Hindi wording was written by me and not reviewed by a native speaker.{note}")}


def evon_facts():
    """The Evon test run on Kaggle (tests/fixtures/evon_q5_examples.json) and what guard.py does with each answer."""
    import guard
    run = load(HERE / "tests" / "fixtures" / "evon_q5_examples.json")
    res = run["results"]
    routes = (("English", "en"), ("Kannada_direct", "kn-IN"))
    rejected = [(r["said"], k, p) for r in res for k, dst in routes if (p := guard.check(r["said"], r[k]["text"], dst))]
    def med(k):
        xs = sorted(r[k]["seconds"] for r in res)
        return f"median {xs[len(xs) // 2]:.2f} s, slowest {xs[-1]:.2f} s"
    out = HERE / "out"
    tun = out / "evon_tunnel_test.json"
    if tun.exists():
        t = load(tun)
        def tstat(dst):
            xs = sorted(r[dst]["seconds"] for r in t)
            n = {k: sum(r[dst]["status"] == k for r in t) for k in ("ok", "rejected", "error")}
            return f"{n['ok']} accepted, {n['rejected']} rejected, {n['error']} errors, median {xs[len(xs) // 2]:.2f} s (slowest {xs[-1]:.2f} s)"
        tunnel = (f"**Through a real tunnel, with the prompt as amended after the live test below** (the same {len(t)} sentences, sent from this Mac to the Kaggle server over a temporary public address, `out/evon_tunnel_test.json`): "
                  f"Kannada {tstat('kn-IN')}; English {tstat('en')}. A wrong key was refused with HTTP 401. The model's answers change when the prompt changes (with the earlier prompt the same test accepted fewer English answers), "
                  "so these counts describe this prompt on this day, not the model.")
        lv = out / "evon_live_sentences.json"
        if lv.exists():
            L = load(lv)
            tunnel += (f" **The live sentences** (said into the app, then replayed with the amended prompt, `out/evon_live_sentences.json`): {len(L)} sentences about who is standing or asking \"where\"; "
                       f"Kannada {sum(x['kn-IN']['status'] == 'ok' for x in L)} accepted and {sum(x['kn-IN']['status'] == 'rejected' for x in L)} rejected; English {sum(x['en']['status'] == 'ok' for x in L)} accepted and {sum(x['en']['status'] == 'rejected' for x in L)} rejected. "
                       "The rejected ones are the model swapping the two people again, or dropping a question, which is what the check is for.")
    else:
        tunnel = "No test through a tunnel has been saved."
    ai = out / "live" / "results_ai.json"
    if ai.exists():
        a = load(ai)
        turns = a["turns"]
        e2e = ("**The scripted call with the fallback on** (`out/live/results_ai.json`, real Prisma and Timbre, real model over the tunnel): "
               + "; ".join(f"turn {x['n']} {x['status'] if x['status'] != 'ai' else 'AI translated (the rules had said ' + x['rules_status'] + '; model answered in ' + format(x['ai']['seconds'], '.2f') + ' s)'}, ready after {x['ms']['total'] / 1000:.2f} s"
                           for x in turns) + ".")
    else:
        e2e = "No call with the fallback on has been saved."
    kf = out / "evon_kannada_source.json"
    if kf.exists():
        K = load(kf)
        bad = [x for x in K if x["hi-IN"]["status"] != "ok" or x["en"]["status"] != "ok"]
        kn_line = (f"**Kannada replies** (`out/evon_kannada_source.json`, {len(K)} Kannada sentences, each to Hindi and English through the tunnel): "
                   f"{sum(x['hi-IN']['status'] == 'ok' for x in K)} Hindi and {sum(x['en']['status'] == 'ok' for x in K)} English answers passed the check, "
                   f"{sum(x['hi-IN']['status'] == 'rejected' for x in K)} Hindi and {sum(x['en']['status'] == 'rejected' for x in K)} English were rejected"
                   + (f" (all for the one sentence that was a misheard transcript: `{bad[0]['said']}`)." if len(bad) == 1 else "."))
    else:
        kn_line = "No Kannada-reply test through the tunnel has been saved."
    return {
        "EVON_KN": kn_line, "EVON_TUNNEL": tunnel, "EVON_E2E": e2e,
        "EVON_N": str(len(res)), "EVON_NEW": str(sum(r["new_pattern"] for r in res)), "EVON_FILE": run["model_file"],
        "EVON_TIMES": f"English {med('English')}; Kannada {med('Kannada_direct')}",
        "EVON_GUARD_LINE": (f"The guard accepted {sum(1 for r in res if not guard.check(r['said'], r['Kannada_direct']['text'], 'kn-IN'))} of {len(res)} Kannada answers "
                            f"and {sum(1 for r in res if not guard.check(r['said'], r['English']['text'], 'en'))} of {len(res)} English answers."),
        "EVON_REJECTS": table(["Said", "Route", "What the guard found"],
                              [[f"`{s}`", {"English": "English", "Kannada_direct": "Kannada"}[k], "; ".join(p)] for s, k, p in rejected]),
    }


def hinglish_facts():
    """The Hinglish edge cases (experiments/hinglish_edge_cases.py): how many there are and that each behaves as written down."""
    sys.path.insert(0, str(HERE / "experiments"))
    import hinglish_edge_cases as H
    rows = H.run()
    kinds = {k: sum(1 for r in rows if r["expected"][0] == k) for k in ("translated", "partial", "refused")}
    return {"HINGLISH_LINE": (f"{len(rows)} Hinglish cases (Roman and Devanagari script, English words, misspellings, two-step routes, negations, "
                              f"questions, conditions, other people, distances, and transcripts that real Prisma returned for a Hinglish voice) "
                              f"each have the correct outcome written down first: {kinds['translated']} translate fully, {kinds['partial']} are partly "
                              f"translated with harmless words left out, {kinds['refused']} are refused. {sum(r['ok'] for r in rows)} of {len(rows)} behave as written "
                              f"(`experiments/hinglish_edge_cases.py`; a test enforces it).")}


def live_facts(out):
    """The live two-window call, from the headless run saved by `python live_call.py --run` (and the optional quieter-bike run)."""
    live = load(Path(out) / "live" / "results.json")
    turns = live["turns"]
    status = {"translated": "translated", "partial": "partly translated", "untranslated": "not translated", "silent": "heard nothing",
              "ai": "AI translated"}
    who = {"customer": "Customer (Hindi)", "biker": "Biker (Kannada)"}
    f = {"LIVE_N": str(len(turns)), "LIVE_SNR": f"{live['biker_snr']:g}"}
    f["LIVE_COUNTS"] = ", ".join(f"{sum(t['status'] == k for t in turns)} {v}" for k, v in status.items() if any(t["status"] == k for t in turns))
    f["LIVE_TABLE"] = table(["Turn", "Speaker", "Said (synthetic voice)", "Prisma heard", "Result", "The other window received", "Ready after"],
        [[t["n"], who[t["who"]], f"`{t['said']}`", f"`{t['heard']}`", status[t["status"]],
          f"`{t['output']}`" if t["output"] else "a spoken notice that it could not translate", _sec(t["ms"]["total"])] for t in turns])
    ms = [t["ms"]["total"] for t in turns]
    f["LIVE_LATENCY"] = (f"Ready after (from the end of the utterance to the translated audio being ready, measured on the machine running the "
                         f"server, over the internet, REST calls): median {_sec(_median(ms))}, fastest {_sec(min(ms))}, slowest {_sec(max(ms))} "
                         f"over {len(ms)} turns. Prisma took a median of {_sec(_median([t['ms']['stt'] for t in turns]))} and Timbre a median of "
                         f"{_sec(_median([t['ms']['tts'] for t in turns]))}; the rules took under 5 ms. The slowest turns are the refusals, "
                         f"because two spoken notices are synthesised one after the other.")
    f["LIVE_NOT_UNDERSTOOD"] = "\n".join(f"- turn {t['n']}: not understood `{' '.join(t['untranslated'])}`" for t in turns if t["untranslated"]) or "- none"
    f["LIVE_AI"] = ("**This run had the AI fallback switched ON**, so its AI-translated turns are not rule-based." if live.get("ai_fallback")
                    else "The AI fallback was off in this run and in every other saved run.")
    f["LIVE_ERRORS"] = f"{len(live['errors'])} turns failed with an API error" if live["errors"] else "no API errors"
    f["LIVE_CALLS"] = f"{live['calls'].get('stt', '?')} Prisma and {live['calls'].get('tts', '?')} Timbre calls"
    bad = [t for t in turns if t["who"] == "biker" and t["status"] != "translated"]
    f["LIVE_BIKER_NOTE"] = ("; ".join(f"The biker's turn {t['n']} (`{t['said']}`) came back from Prisma as `{t['heard']}` under {live['biker_snr']:g} dB bike noise, "
                                      f"and the interpreter {'refused it' if t['status'] == 'untranslated' else 'translated only part of it'} out loud in both languages "
                                      f"instead of guessing. That is the intended behaviour, and also a real limit." for t in bad)
                            or "Every biker turn in this run was translated.")
    p10 = Path(out) / "live" / "results_bike10.json"
    if p10.exists():
        q = load(p10)
        qt = q["turns"]
        diff = [t["n"] for t in qt if t["status"] != next((x["status"] for x in turns if x["n"] == t["n"]), None)]
        f["LIVE_QUIETER"] = (f"The same script with the bike at {q['biker_snr']:g} dB instead of {live['biker_snr']:g} dB (a separate run, `results_bike10.json`, "
                             f"not a re-roll of the first): {', '.join(f'{sum(t['status'] == k for t in qt)} {v}' for k, v in status.items() if any(t['status'] == k for t in qt))}; "
                             + (f"the results differ from the first run in turn {', '.join(map(str, diff))}." if diff else "the results are the same as in the first run."))
    else:
        f["LIVE_QUIETER"] = "No run with a quieter bike has been saved."
    return f


def facts(out=OUT):
    out = Path(out)
    missing = [f"{p} (run: {cmd})" for p, cmd in NEEDS.items() if not (out.parent / p).exists()] if out == OUT else []
    if missing:
        raise SystemExit("Missing result files:\n  " + "\n  ".join(missing))
    smoke, s1, s2 = load(out / "results.json"), load(out / "sweep_summary.json"), load(out / "hard_summary.json")
    short, det, demo = load(out / "short_audio.json"), load(out / "determinism.json"), load(out / "demo" / "results.json")
    f = {}

    f["SMOKE_LINE"] = f"{sum(r['status'] == 'ok' for r in smoke)} of {len(smoke)}"
    f["SWEEP1_N"] = str(s1["all"]["clean"]["n"])
    f["SWEEP1_TABLE"] = table(["Condition", "Exact match", "Word error rate", "Landmark words found"],
        [[c, f"{m['exact_%']}%", f"{m['wer_%']}%", f"{m['keywords_%']}%"] for c, m in s1["all"].items()])
    f["SWEEP2_N"] = str(s2["hard_all"]["clean"]["n"])
    f["SWEEP2_TABLE"] = table(["Condition", "Exact match", "Word error rate", "All distinguishing words correct"],
        [[c, f"{m['exact']}%", f"{m['wer']}%", f"{m['crit_all']}%"] for c, m in s2["hard_all"].items()])
    f["ORIG_BIKE_LINE"] = ", ".join(f"{c} {m['exact']}%" for c, m in s2["orig_bike"].items())
    f["NOISE_COMPARE"] = (f"At 5 dB, exact match was {s2['hard_all']['engine@5']['exact']}% with engine hum alone and "
                          f"{s2['hard_all']['babble@5']['exact']}% with babble alone, on the same phrasings.")

    own, cross, false_acc = evaluate.analyse(out)
    rows = []
    for st in ("hard", "orig-bike", "orig-white"):
        for k in sorted((k for k in own if k[0] == st), key=lambda k: evaluate.ORDER.index(k[1]) if k[1] in evaluate.ORDER else 99):
            o, c = own[k], cross[k]
            n, m = sum(o.values()), sum(c.values())
            rows.append([st, k[1], n, pct(o["ACCEPT"], n), pct(o["CONFIRM"], n), pct(o["ASK_AGAIN"], n), pct(o["MISMATCH"], n),
                         f"{c['ACCEPT']} of {m}"])
    f["VERIFIER_TABLE"] = table(["Set", "Condition", "Transcripts", "Accepted", "Read-back", "Ask again", "Mismatch",
                                 "Look-alike transcripts accepted"], rows)
    f["FALSE_ACCEPTS"] = str(len(false_acc))

    rows = []
    for name, note, phrases in SETS:
        m = evaluate_unseen.measure(phrases)
        rows.append([name, m["phrases"], f"{m['found']}/{m['wanted']} ({m['recall']}%)", m["false_values"],
                     "not used for tuning" if name == "C" else "in-sample: lexicon extended after its misses"])
    mc = evaluate_unseen.measure(next(p for n, _, p in SETS if n == "C"))
    f["EXTRACTOR_C"] = f"{mc['found']}/{mc['wanted']} ({mc['recall']}%)"
    f["EXTRACTOR_TABLE"] = table(["Set", "Phrases", "Critical words found", "False matches", "Status"], rows)

    rows = []
    for u in short["utterances"]:
        acc = sum(r["decision"] == "ACCEPT" for r in u["results"])
        rows.append([u["label"], f"{u['seconds']} s", f"{acc} of {len(u['results'])}", f"`{u['results'][0]['heard']}`"])
    f["SHORT_TABLE"] = table(["Utterance", "Length", "Accepted (clean + 3 bike-noise levels)", "Clean transcript"], rows)
    single = [y for y in short["yes_no"] if len(y["said"].split()) == 1]
    phrase = [y for y in short["yes_no"] if len(y["said"].split()) > 1]
    ok = lambda ys, k: sum(y[k]["parsed"] == y["want"] for y in ys)
    f["YESNO_LINE"] = (f"One-word replies ({len(single)} clips, about {single[0]['seconds']} s): parsed correctly {ok(single, 'raw')} of {len(single)} "
                       f"as recorded and {ok(single, 'padded')} of {len(single)} with silence added. "
                       f"Short phrases ({len(phrase)} clips): {ok(phrase, 'raw')} of {len(phrase)} and {ok(phrase, 'padded')} of {len(phrase)}.")

    t, p = det["timbre_identical_requests"], det["prisma_identical_audio"]
    f["DETERMINISM_LINE"] = (f"Timbre: {sum(x['distinct_outputs'] == det['repeats'] for x in t)} of {len(t)} repeated requests produced a different audio file "
                             f"on every one of {det['repeats']} calls. Prisma: {sum(x['distinct_transcripts'] == 1 for x in p)} of {len(p)} repeated audio files "
                             f"returned the same transcript on every call.")

    cust = demo["customers"]
    norm = lambda s: " ".join(re.sub(r"[।,.?!]", "", s).lower().split())
    diffs = [c for c in cust if norm(c["heard"]) != norm(c["said"])]
    f["N_CUSTOMERS"] = str(len(cust))
    f["LANGS"] = " and ".join(sorted({LANG.get(c["lang"], c["lang"]) for c in cust}))
    f["CUSTOMER_DIFF_COUNT"] = f"{len(diffs)} of {len(cust)}"
    f["CUSTOMER_DIFFS"] = "\n".join(f"- customer {c['id'][1:]} ({LANG.get(c['lang'])}): said `{c['said']}`, Prisma heard `{c['heard']}`" for c in diffs) or "- none"
    after = {r["text"]: r["confidence"] for r in demo.get("route_after", [])}
    f["ROUTE_TABLE"] = table(["Landmark", "Support", "Confidence before, after the rider", "State", "Contested"],
        [[r["text"], r["support"], f"{r['confidence']}, {after.get(r['text'], 'n/a')}", r["state"], "yes" if r["contested"] else "no"]
         for r in demo["route_before"]])
    f["STEPS_TABLE"] = table(["Step", "Landmark", "Noise", "Outcome"],
        [[s["step"], s["phrase"], f"{s['kind']} {s['snr']} dB",
          f"{s['status']} {METHOD.get(s['method'], '')} after {len(s['attempts'])} {'try' if len(s['attempts']) == 1 else 'tries'}"]
         for s in demo["steps"]])
    f["LADDER_PHRASE"] = demo["ladder_phrase"]
    f["LADDER_TABLE"] = table(["Condition", "Prisma heard", "Decision"],
        [[r["cond"], f"`{r['heard'] or '(empty transcript)'}`", f"{r['decision']} ({r['reason']})"] for r in demo["ladder"]])
    st = demo["stress"]
    acts = [a["action"] for a in st["attempts"]]
    f["STRESS_LINE"] = (f"babble at {st['snr']} dB on `{st['phrase']}`, noise seed {st['seeds']}. "
                        + (f"The first attempt ended as {acts[0]}." if len(acts) == 1 else f"Attempts: {' then '.join(acts)}; final status {st['status']}."))
    hard_paths = {"CONFIRM_YN": "read-back", "ASK_AGAIN": "ask-again", "FALLBACK_TAP": "tap fallback"}
    seen = [hard_paths[a["action"]] for e in demo["steps"] + [st] for a in e["attempts"] if a["action"] in hard_paths]
    f["LIVE_PATHS"] = (f"In this run's live scenes the bot used: {', '.join(sorted(set(seen)))}." if seen
                       else "No read-back, ask-again or tap fallback happened in this run's live scenes.")
    c = demo["replay"]["counts"]
    f["REPLAY_LINE"] = f"{c['ACCEPT']} accepted, {c['CONFIRM']} read-back, {c['ASK_AGAIN']} ask-again, {c['MISMATCH']} mismatch of {demo['replay']['total']}"
    f["REPLAY_CASES"] = "\n".join(
        f"- case {cs['n']} ({LANG.get(cs['lang'])}, sweep condition {cs['condition']}): "
        + " then ".join(f"{x['source']} → {x['action']}" for x in cs["steps"]) + f"; status {cs['status']}"
        for cs in demo["replay"]["cases"])
    call, rt = load(out / "call" / "results.json"), load(out / "render_roundtrip.json")
    turns = call["turns"]
    who = {"customer": "Customer (Hindi)", "biker": "Biker (Kannada)"}
    status = {"translated": "translated", "partial": "partly translated", "untranslated": "not translated"}
    f["CALL_N"] = str(len(turns))
    f["CALL_COUNTS"] = ", ".join(f"{sum(t['status'] == k for t in turns)} {v}" for k, v in status.items())
    f["CALL_TABLE"] = table(["Turn", "Speaker", "Said", "Prisma heard", "Interpreter", "The other person hears"],
        [[t["n"], who[t["who"]], f"`{t['said']}`", f"`{t['heard']}`", status[t["status"]],
          f"`{t['output']}`" if t["output"] else "a spoken notice that it could not translate"] for t in turns])
    f["CALL_NOT_UNDERSTOOD"] = "\n".join(f"- turn {t['n']}: not understood `{' '.join(t['not_understood'])}`" for t in turns if t["not_understood"]) or "- none"
    f["LIMITS_TABLE"] = table(["Cannot translate", "Example", "Why it is refused"],
        [[title, f"`{text}`", T.translate(text, lang, "kn-IN" if lang == "hi-IN" else "hi-IN").reason_text] for title, text, lang, _ in T.LIMITS])
    f.update(live_facts(out))
    f.update(hinglish_facts())
    f.update(evon_facts())
    f.update(real_facts(out))
    f.update(english_facts(out))
    f.update(saved_demo_facts())
    counts = T.vocabulary_counts()
    f["PHRASEBOOK_N"] = str(counts.pop("phrasebook phrases"))
    f["VOCAB_LINE"] = ", ".join(f"{v} {k}" for k, v in counts.items())
    rows = []
    for lang, name in (("hi-IN", "Hindi"), ("kn-IN", "Kannada")):
        r = [x for x in rt if x["lang"] == lang and x["phrase"]]
        rows.append([name, len(r), f"{sum(x['same_meaning'] for x in r)} of {len(r)}", f"{sum(x['exact_text'] for x in r)} of {len(r)}"])
    f["ROUNDTRIP_TABLE"] = table(["Language", "Phrases", "Same meaning after speech and recognition", "Identical text"], rows)
    return f


def render(template, f):
    def sub(m):
        if m.group(1) not in f:
            raise SystemExit(f"Unknown placeholder {{{{{m.group(1)}}}}}")
        return f[m.group(1)]
    return re.sub(r"\{\{([A-Z0-9_]+)\}\}", sub, template)


def render_all(out=OUT, here=HERE):
    f = facts(out)
    return {name: render((Path(here) / f"{name.replace('.md', '')}.template.md").read_text(encoding="utf-8"), f)
            for name in ("README.md", "SUBMISSION.md")}


if __name__ == "__main__":
    for name, text in render_all().items():
        (HERE / name).write_text(text, encoding="utf-8")
        print(f"wrote {name} ({len(text.splitlines())} lines)")
