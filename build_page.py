"""Build out/demo/index.html: one self-contained page for the 60-second video.

Everything on the page comes from out/demo/results.json (the real run) and the WAV files next to it.
Waveforms are computed from those files. Nothing is typed in by hand: if a scene is not in the results
(stress, replay) it does not appear.

    python demo.py --stress --replay      # produce the results (cached after the first run)
    python build_page.py                  # write out/demo/index.html
    python -m http.server 8765 --directory out/demo      # or just double-click index.html
"""
import json
import sys
from pathlib import Path

import gnani

BUCKETS = 96


def peaks(path):
    samples, _ = gnani.read_wav(Path(path).read_bytes())
    if not samples:
        return []
    size = max(1, len(samples) // BUCKETS)
    p = [max((abs(x) for x in samples[i * size:(i + 1) * size]), default=0) for i in range(BUCKETS)]
    top = max(p) or 1
    return [round(x / top, 3) for x in p]


def wav_files(node, found=None):
    """Every string in the results that names a .wav file."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for v in node.values():
            wav_files(v, found)
    elif isinstance(node, list):
        for v in node:
            wav_files(v, found)
    elif isinstance(node, str) and node.endswith(".wav") and "/" not in node:
        found.add(node)
    return found


def build(out_dir):
    out = Path(out_dir)
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    if "error" in res:
        raise SystemExit(f"The demo run has no route: {res['error']}")
    pk, dur, missing = {}, {}, []
    for name in sorted(wav_files(res)):
        path = out / name
        if not path.exists():
            missing.append(name)
            continue
        pk[name] = peaks(path)
        samples, sr = gnani.read_wav(path.read_bytes())
        dur[name] = round(len(samples) / sr, 2)
    data = json.dumps({"res": res, "peaks": pk, "dur": dur, "missing": missing}, ensure_ascii=False)
    html = TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))
    target = out / "index.html"
    target.write_text(html, encoding="utf-8")
    return target, missing


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landmark Chain demo</title>
<style>
:root{--bg:#f5f2ec;--surface:#fff;--ink:#1c1e22;--muted:#5b6370;--line:#e4dfd5;--accent:#c4501b;--accent-soft:#fbe9df;
--wave:#c9c3b6;--ok:#17724a;--ok-bg:#e3f4ea;--warn:#8a5a0a;--warn-bg:#fcf0d6;--bad:#a12b1f;--bad-bg:#fbe4e0;--info:#244f9e;--info-bg:#e4ecfa;
--shadow:0 1px 2px rgba(20,20,20,.05),0 8px 24px rgba(20,20,20,.06)}
@media (prefers-color-scheme:dark){:root{--bg:#0f1217;--surface:#171b22;--ink:#eef0f3;--muted:#9ba4b3;--line:#272d38;--accent:#ff8d5c;--accent-soft:#33211a;
--wave:#3a4252;--ok:#6fdca4;--ok-bg:#12301f;--warn:#f0c26a;--warn-bg:#352a0e;--bad:#ff9a8c;--bad-bg:#3a1713;--info:#8db4ff;--info-bg:#16264a;--shadow:none}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Inter",system-ui,-apple-system,"Segoe UI","Noto Sans Devanagari","Kohinoor Devanagari",sans-serif;padding-bottom:64px}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:20px;padding:12px 24px;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.logo{width:34px;height:34px;border-radius:10px;background:var(--accent);position:relative;flex:none}
.logo:before,.logo:after{content:"";position:absolute;width:8px;height:8px;border-radius:50%;background:#fff}
.logo:before{left:7px;bottom:7px}.logo:after{right:7px;top:7px}
.brand b{display:block;font-size:17px;line-height:1.2}.brand small{color:var(--muted);font-size:12px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin-left:auto}
nav a{color:var(--muted);text-decoration:none;font-size:13px;padding:5px 11px;border-radius:99px;border:1px solid transparent}
nav a:hover,nav a.on{color:var(--ink);border-color:var(--line);background:var(--surface)}
button{font:inherit;cursor:pointer}
.primary{background:var(--accent);color:#fff;border:0;border-radius:99px;padding:9px 20px;font-weight:600;font-size:14px}
.primary[disabled]{opacity:.55;cursor:default}
.ghost{background:transparent;color:var(--ink);border:1px solid var(--line);border-radius:99px;padding:8px 16px;font-size:14px}
main{max-width:1120px;margin:0 auto;padding:0 24px}
.hero{padding:56px 0 24px}
.hero h1{font-size:clamp(30px,5vw,50px);line-height:1.1;margin:0 0 14px;letter-spacing:-.02em;max-width:18em}
.hero p{color:var(--muted);font-size:18px;max-width:42em;margin:0}
section{padding:36px 0 8px;scroll-margin-top:84px}
.sh{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.num{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--ink);color:var(--bg);font-size:13px;font-weight:700;flex:none}
h2{font-size:24px;margin:0;letter-spacing:-.01em}
.lead{color:var(--muted);margin:2px 0 18px 40px;max-width:46em}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.card{min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow);transition:border-color .2s,box-shadow .2s,transform .2s}
.card.active{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),var(--shadow)}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sp{justify-content:space-between}
.chip{display:inline-flex;align-items:center;gap:5px;border-radius:99px;padding:2px 10px;font-size:12.5px;font-weight:600;white-space:nowrap}
.chip.ok{color:var(--ok);background:var(--ok-bg)}.chip.warn{color:var(--warn);background:var(--warn-bg)}
.chip.bad{color:var(--bad);background:var(--bad-bg)}.chip.info{color:var(--info);background:var(--info-bg)}.chip.mute{color:var(--muted);background:var(--line)}
.lab{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:10px 0 2px}
.txt{font-size:18px;line-height:1.45}
.w.diff{background:var(--warn-bg);color:var(--warn);border-radius:4px;padding:0 3px}
.wavebox{display:flex;align-items:center;gap:10px;margin:10px 0 4px}
.wavebox canvas{flex:1;height:44px;min-width:0;display:block}
.pbtn{flex:none;width:36px;height:36px;border-radius:50%;border:0;background:var(--accent);color:#fff;display:grid;place-items:center;padding:0}
.pbtn svg{width:14px;height:14px;fill:#fff}
.dur{font-size:12px;color:var(--muted);flex:none;width:34px;text-align:right}
.route{display:grid;gap:0;position:relative;margin-left:4px}
.step{display:grid;grid-template-columns:44px minmax(0,1fr);gap:14px;position:relative;padding-bottom:16px}
.step:not(:last-child):before{content:"";position:absolute;left:21px;top:44px;bottom:-2px;width:2px;background:var(--line)}
.dot{width:44px;height:44px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:700;z-index:1}
.reveal.anim .step{animation:rise .5s ease backwards}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
.bar{height:8px;border-radius:99px;background:var(--line);overflow:hidden;margin-top:8px;position:relative}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--accent);border-radius:99px}
.bar i.ghost{background:var(--wave)}
.small{font-size:13px;color:var(--muted)}
.attempt{display:grid;grid-template-columns:minmax(200px,1.1fr) 1.4fr 1fr;gap:16px;padding:12px 0;border-top:1px solid var(--line);align-items:start}
.attempt:first-of-type{border-top:0}
@media (max-width:820px){.attempt{grid-template-columns:1fr}.top{flex-wrap:wrap;position:static}nav{margin-left:0}}
.ladder{display:grid;gap:10px}
.lrow{display:grid;grid-template-columns:150px minmax(180px,1fr) 1.2fr 150px;gap:14px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 16px}
.lrow>*,.attempt>*{min-width:0}
.lrow.active{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
@media (max-width:900px){.lrow{grid-template-columns:1fr}}
.banner{border:2px dashed var(--warn);background:repeating-linear-gradient(135deg,var(--warn-bg),var(--warn-bg) 12px,transparent 12px,transparent 24px);border-radius:14px;padding:14px 18px;margin:0 0 16px;font-weight:700;color:var(--warn);letter-spacing:.02em}
.banner span{display:block;font-weight:400;color:var(--ink);margin-top:4px;letter-spacing:0}
.stack{display:flex;height:34px;border-radius:10px;overflow:hidden;margin:6px 0 8px;border:1px solid var(--line)}
.stack div{display:grid;place-items:center;font-size:12px;font-weight:700;min-width:0;overflow:hidden}
.src{font-size:12px;border:1px solid var(--line);border-radius:6px;padding:1px 7px;color:var(--muted);white-space:nowrap}
.src.rec{color:var(--info);border-color:var(--info)}.src.scr{color:var(--warn);border-color:var(--warn);border-style:dashed}
.notes{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:6px 22px 14px}
.notes li{margin:9px 0;color:var(--ink)}
.cap{position:fixed;left:0;right:0;bottom:0;z-index:6;background:var(--ink);color:var(--bg);text-align:center;font-size:13px;padding:9px 16px}
footer{padding:36px 0;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<header class="top">
  <div class="brand"><div class="logo"></div><div><b>Landmark Chain</b><small>Built on Gnani Prisma and Timbre</small></div></div>
  <nav id="nav" aria-label="Scenes"></nav>
  <div class="row"><button id="play" class="primary" aria-label="Play the whole demo">Play the demo</button><button id="stop" class="ghost" hidden>Stop</button></div>
</header>
<main>
  <div class="hero">
    <h1>Delivery fails when an address is a landmark.</h1>
    <p>Customers describe a house in their own language. Prisma hears them, the landmarks merge into one route, and a rider confirms each landmark by voice. Every transcript, decision and clip on this page comes from a real run.</p>
  </div>
  <div id="app"></div>
  <footer>Generated from <code>results.json</code> by <code>build_page.py</code>. Audio: Gnani Timbre (synthetic voices) with simulated noise. Transcripts: Gnani Prisma.</footer>
</main>
<div class="cap">Synthetic voices and simulated noise. Transcripts by Gnani Prisma. No real customer data.</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const R = D.res;
const LANG = {'hi-IN':'Hindi','mr-IN':'Marathi'};
const $ = (s, r = document) => r.querySelector(s);
const sleep = ms => new Promise(r => setTimeout(r, ms));
function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) { if (kid == null || kid === false) continue; e.append(kid.nodeType ? kid : document.createTextNode(kid)); }
  return e;
}
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* ---------- audio + waveforms ---------- */
const players = {}, waves = {};
function player(file) { return players[file] || (players[file] = new Audio(file)); }
function drawWave(c, peaks, progress) {
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth, hh = c.clientHeight;
  if (!w) return;
  c.width = w * dpr; c.height = hh * dpr;
  const g = c.getContext('2d'); g.scale(dpr, dpr);
  const n = peaks.length, bw = w / n;
  for (let i = 0; i < n; i++) {
    const ph = Math.max(3, peaks[i] * hh * 0.92);
    g.fillStyle = (i / n < progress) ? css('--accent') : css('--wave');
    g.fillRect(i * bw + 1, (hh - ph) / 2, Math.max(1, bw - 2), ph);
  }
}
function redrawAll() { for (const f in waves) for (const w of waves[f]) drawWave(w.c, D.peaks[f] || [], w.p || 0); }
function setProgress(file, p) { for (const w of (waves[file] || [])) { w.p = p; drawWave(w.c, D.peaks[file] || [], p); } }
function playClip(file) {
  return new Promise(res => {
    const a = player(file);
    for (const f in players) if (f !== file) { players[f].pause(); }
    a.onended = () => { setProgress(file, 0); res(); };
    a.onerror = () => res();
    a.ontimeupdate = () => setProgress(file, a.duration ? a.currentTime / a.duration : 0);
    a.currentTime = 0;
    a.play().catch(() => res());
  });
}
function toggleClip(file) {
  const a = player(file);
  if (!a.paused) { a.pause(); a.currentTime = 0; setProgress(file, 0); return; }
  playClip(file);
}
const ICON = '<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5v11l9-5.5z"/></svg>';
function clip(file, label) {
  if (!file) return null;
  if (!D.peaks[file]) return h('div', {class: 'small', text: 'audio file missing: ' + file});
  const c = h('canvas', {'aria-hidden': 'true'});
  (waves[file] = waves[file] || []).push({c, p: 0});
  const b = h('button', {class: 'pbtn', 'aria-label': 'Play ' + (label || file), onclick: () => toggleClip(file)});
  b.innerHTML = ICON;
  return h('div', {class: 'wavebox'}, b, c, h('span', {class: 'dur', text: (D.dur[file] || 0).toFixed(1) + 's'}));
}

/* ---------- small helpers ---------- */
const ACTION = {
  CONFIRMED: ['Confirmed', 'ok', '✓'], ACCEPT: ['Accepted', 'ok', '✓'], CONFIRM_YN: ['Read-back', 'info', '?'],
  ASK_AGAIN: ['Asks again', 'warn', '↻'], MISMATCH: ['Mismatch', 'bad', '✕'], FALLBACK_TAP: ['Tap fallback', 'warn', '↻'],
  NOT_FOUND: ['Not found', 'bad', '✕'], UNRESOLVED: ['Stops here', 'warn', '↻'], AWAITING_TAP: ['Waiting for tap', 'warn', '↻'],
};
function chip(kind, extra) {
  const [t, c, s] = ACTION[kind] || [kind, 'mute', ''];
  return h('span', {class: 'chip ' + c}, s + ' ' + t + (extra ? ' ' + extra : ''));
}
const strip = w => w.replace(/[।,.?!]/g, '').toLowerCase();
function heardText(said, heard) {
  if (!heard) return h('span', {class: 'small', text: '(empty transcript)'});
  const set = new Set(said.split(/\s+/).map(strip));
  return h('span', {}, heard.split(/\s+/).filter(Boolean).map(w => h('span', {class: set.has(strip(w)) ? 'w' : 'w diff'}, w + ' ')));
}
const METHOD = {voice: 'by voice', yes: 'by a spoken yes', tap: 'by tap (simulated)'};
function section(id, n, title, lead) {
  return h('section', {id}, h('div', {class: 'sh'}, h('span', {class: 'num', text: n}), h('h2', {text: title})), lead ? h('p', {class: 'lead', text: lead}) : null);
}
const registry = [];   // groups played in order by "Play the demo"

/* ---------- scene 1: customers ---------- */
function sceneCustomers() {
  const s = section('s1', '1', 'Customers describe the house', 'Four synthetic voices, two languages, phone-line audio. Prisma\'s transcript is shown against what was said; highlighted words differ.');
  const g = h('div', {class: 'grid'});
  for (const c of R.customers) {
    const card = h('div', {class: 'card'},
      h('div', {class: 'row sp'}, h('b', {text: 'Customer ' + c.id.replace('c', '')}), h('span', {class: 'chip mute', text: (LANG[c.lang] || c.lang) + ' · ' + (c.voice || '')})),
      clip(c.audio, 'customer ' + c.id),
      h('div', {class: 'lab', text: 'Said'}), h('div', {class: 'txt', text: c.said}),
      h('div', {class: 'lab', text: 'Prisma heard'}), h('div', {class: 'txt'}, heardText(c.said, c.heard)));
    g.append(card);
    registry.push({el: card, files: [c.audio]});
  }
  s.append(g);
  return s;
}

/* ---------- scene 2: merged route ---------- */
function sceneRoute() {
  const langs = [...new Set(R.customers.map(c => LANG[c.lang] || c.lang))].join(' and ');
  const s = section('s2', '2', 'One route from many voices', R.customers.length + ' customers (' + langs + ') merged into a single route. Confidence moves with evidence, and a rider\'s confirmation raises it.');
  const wrap = h('div', {class: 'route reveal'});
  R.route_before.forEach((r, i) => {
    const after = (R.route_after || []).find(a => a.text === r.text);
    const st = r.state === 'consensus' ? 'ok' : 'warn';
    wrap.append(h('div', {class: 'step'}, h('div', {class: 'dot', text: String(i + 1)}),
      h('div', {class: 'card'},
        h('div', {class: 'row sp'}, h('span', {class: 'txt'}, h('b', {text: r.text})),
          h('span', {class: 'row'}, h('span', {class: 'chip ' + st, text: r.state}), r.contested ? h('span', {class: 'chip warn', text: 'contested'}) : null,
            r.alternatives ? h('span', {class: 'chip mute', text: r.alternatives + ' other version' + (r.alternatives > 1 ? 's' : '')}) : null)),
        h('div', {class: 'small', text: 'support ' + r.support + ' · confidence ' + r.confidence + (after ? ' → ' + after.confidence + ' after the rider confirmed' : '')}),
        h('div', {class: 'bar'}, h('i', {class: 'ghost', style: 'width:' + Math.round((after ? after.confidence : r.confidence) * 100) + '%'}), h('i', {style: 'width:' + Math.round(r.confidence * 100) + '%'})))));
  });
  s.append(wrap);
  registry.push({el: wrap, files: [], onEnter: () => { wrap.classList.remove('anim'); void wrap.offsetWidth; wrap.querySelectorAll('.step').forEach((e, i) => e.style.animationDelay = i * 0.35 + 's'); wrap.classList.add('anim'); }, pause: 1800});
  return s;
}

/* ---------- scene 3 + 4: rider steps ---------- */
function riderCard(e, opts = {}) {
  const attempts = e.attempts.map(a => {
    const pa = a.prompt_audio || (a.prompt && a.prompt === e.done_text ? e.done_audio : null);
    const bot = a.prompt ? h('div', {}, h('div', {class: 'lab', text: 'Bot says'}), h('div', {text: a.prompt}), pa ? clip(pa, 'bot prompt') : null) : null;
    return h('div', {class: 'attempt'},
      h('div', {}, h('div', {class: 'small', text: 'Try ' + a.n}), clip(a.audio, 'rider try ' + a.n)),
      h('div', {}, h('div', {class: 'lab', text: 'Rider said'}), h('div', {class: 'small', text: a.said}),
        h('div', {class: 'lab', text: 'Prisma heard'}), h('div', {class: 'txt'}, heardText(a.said, a.heard))),
      h('div', {}, chip(a.action), h('div', {class: 'small', style: 'margin-top:4px', text: a.reason ? '(' + a.reason + ')' : ''}), bot));
  });
  const files = [e.next_audio];
  e.attempts.forEach(a => { files.push(a.audio); if (a.prompt_audio) files.push(a.prompt_audio); });
  if (e.done_audio) files.push(e.done_audio);   // played once, after the last attempt
  const status = e.status === 'AWAITING_TAP' ? chip('AWAITING_TAP', '(button press not simulated)') : chip('CONFIRMED', e.method ? METHOD[e.method] || '' : '');
  const title = opts.stress ? 'Stress test' : 'Step ' + e.step;
  const card = h('div', {class: 'card', style: 'margin-bottom:14px'},
    h('div', {class: 'row sp'}, h('span', {class: 'txt'}, h('b', {text: title + ' · ' + e.phrase})),
      h('span', {class: 'row'}, h('span', {class: 'chip mute', text: (e.kind === 'babble' ? 'Babble' : 'Bike noise') + ' ' + e.snr + ' dB'}), status)),
    h('div', {class: 'row', style: 'margin-top:6px'}, h('span', {class: 'small', text: 'Bot: ' + (e.next_text || '')}), clip(e.next_audio, 'bot prompt')),
    ...attempts,
    e.tap_fallback && e.status !== 'AWAITING_TAP' ? h('div', {class: 'small', text: 'Tap fallback was reached; the button press is simulated.'}) : null);
  registry.push({el: card, files});
  return card;
}
function sceneRider() {
  const s = section('s3', '3', 'The rider confirms each landmark', 'A ' + (LANG[R.rider_lang] || R.rider_lang) + ' rider on a bike hears the route in their language and repeats each landmark through simulated bike noise.');
  R.steps.forEach(e => s.append(riderCard(e)));
  return s;
}

/* ---------- scene 4: noise ladder ---------- */
function sceneLadder() {
  const s = section('s4', '4', 'The same landmark in four noise conditions', 'Landmark: ' + R.ladder_phrase + '. The rider says: ' + (R.ladder_said || '') + '. Decisions are made by the verifier on Prisma\'s transcript.');
  const box = h('div', {class: 'ladder'});
  for (const r of R.ladder) {
    const row = h('div', {class: 'lrow'},
      h('div', {}, h('b', {text: (r.kind === 'babble' ? 'Babble' : 'Bike noise') + ' ' + r.snr + ' dB'})),
      clip(r.audio, r.cond),
      h('div', {}, h('div', {class: 'lab', style: 'margin-top:0', text: 'Prisma heard'}), h('div', {class: 'txt'}, heardText(R.ladder_said || '', r.heard))),
      h('div', {}, chip(r.decision), h('div', {class: 'small', style: 'margin-top:4px', text: '(' + r.reason + ')'})));
    box.append(row);
    registry.push({el: row, files: [r.audio]});
  }
  s.append(box);
  return s;
}

/* ---------- scene 5: stress ---------- */
function sceneStress() {
  const st = R.stress;
  const s = section('s5', '5', 'Stress test: one run, not re-rolled', 'Babble at 5 dB on the landmark with the most critical words (chosen by a rule fixed in advance). Seeds ' + JSON.stringify(st.seeds) + '. Whatever happened is shown, and it was not added to the store.');
  s.append(riderCard(st, {stress: true}));
  return s;
}

/* ---------- scene 6: replay ---------- */
function sceneReplay() {
  const rp = R.replay;
  const s = section('s6', R.stress ? '6' : '5', 'Replay of recorded cases');
  s.append(h('div', {class: 'banner'}, rp.label, h('span', {text: 'Recorded Prisma transcripts from the earlier 24-phrase noise sweep. Prisma was not called for them. The sweep did not save its audio, so only the bot\'s prompts are audio.'})));
  if (rp.error) { s.append(h('p', {text: 'Not run: ' + rp.error})); return s; }
  const c = rp.counts, T = rp.total || 1;
  const parts = [['ACCEPT', 'Accepted', 'var(--ok-bg)', 'var(--ok)'], ['CONFIRM', 'Read-back', 'var(--info-bg)', 'var(--info)'], ['ASK_AGAIN', 'Ask again', 'var(--warn-bg)', 'var(--warn)'], ['MISMATCH', 'Mismatch', 'var(--bad-bg)', 'var(--bad)']];
  s.append(h('div', {class: 'small', text: 'All ' + rp.total + ' recorded transcripts, checked against the phrase that was spoken:'}),
    h('div', {class: 'stack'}, parts.filter(p => c[p[0]]).map(p => h('div', {style: 'flex:' + c[p[0]] + ';background:' + p[2] + ';color:' + p[3], title: p[1] + ' ' + c[p[0]], text: c[p[0]] / T >= 0.04 ? c[p[0]] : ''}))),
    h('div', {class: 'row small', style: 'gap:16px;flex-wrap:wrap'}, parts.map(p => h('span', {text: p[1] + ' ' + c[p[0]] + ' (' + Math.round(100 * c[p[0]] / T) + '%)'}))),
    h('p', {class: 'small', text: 'Cases shown: the first read-back and the first ask-again in file order, chosen before looking.'}));
  const g = h('div', {class: 'grid', style: 'margin-top:12px'});
  rp.cases.forEach(cs => {
    const files = [];
    const steps = cs.steps.map(st => {
      if (st.prompt_audio) files.push(st.prompt_audio);
      return h('div', {style: 'margin:10px 0'}, h('span', {class: 'src ' + (st.source.startsWith('recorded') ? 'rec' : 'scr'), text: st.source}),
        h('div', {class: 'txt', text: st.text || '(empty transcript)'}), h('div', {class: 'row', style: 'margin-top:4px'}, chip(st.action), h('span', {class: 'small', text: st.reason ? '(' + st.reason + ')' : ''})),
        st.bot_says ? h('div', {class: 'small', style: 'margin-top:4px', text: 'Bot says: ' + st.bot_says}) : null, st.prompt_audio ? clip(st.prompt_audio, 'bot prompt') : null);
    });
    const card = h('div', {class: 'card'}, h('div', {class: 'row sp'}, h('b', {text: 'Case ' + cs.n + ' · ' + (LANG[cs.lang] || cs.lang)}), h('span', {class: 'chip mute', text: cs.condition})),
      h('div', {class: 'small', text: 'Expected: ' + cs.expected + ' · sweep file line ' + cs.sweep_csv_line}), ...steps,
      h('div', {class: 'row', style: 'margin-top:8px'}, chip(cs.status)), cs.note ? h('div', {class: 'small', text: cs.note}) : null);
    g.append(card);
    registry.push({el: card, files});
  });
  s.append(g);
  return s;
}

/* ---------- notes, derived from the data ---------- */
function sceneNotes() {
  const all = R.steps.concat(R.stress ? [R.stress] : []);
  const readback = all.some(e => e.attempts.some(a => a.action === 'CONFIRM_YN'));
  const diffs = R.customers.filter(c => strip(c.heard).replace(/\s+/g, ' ') !== strip(c.said).replace(/\s+/g, ' ')).length;
  const notAccepted = R.ladder.filter(r => r.decision !== 'ACCEPT');
  const li = [];
  li.push('All voices are Gnani Timbre output and the noise is simulated (engine hum and babble built from other synthetic voices). Transcripts are real Gnani Prisma output. Nothing here was recorded from a real rider or customer.');
  li.push(diffs + ' of ' + R.customers.length + ' customer transcripts differ from what was said' + (diffs ? ' (highlighted above); the merged route still came out as shown.' : '.'));
  li.push(notAccepted.length ? 'Noise ladder: ' + notAccepted.map(r => r.cond + ' → ' + (ACTION[r.decision] || [r.decision])[0].toLowerCase() + (r.heard ? ' (Prisma heard "' + r.heard + '")' : ' (empty transcript)')).join('; ') + '. The bot asks again instead of guessing.' : 'Every noise condition in the ladder was accepted.');
  li.push(readback ? 'A read-back happened in this run\'s live scenes.' : 'No read-back was needed in this run\'s live scenes' + (R.replay && R.replay.cases && R.replay.cases.length ? '; the replay shows recorded cases.' : '.'));
  if (all.some(e => e.tap_fallback)) li.push('A tap fallback was reached; the rider\'s button press is simulated.');
  if (D.missing && D.missing.length) li.push('Missing audio files: ' + D.missing.join(', '));
  const s = h('section', {id: 'notes'}, h('div', {class: 'sh'}, h('span', {class: 'num', text: '!'}), h('h2', {text: 'What this run does and does not show'})));
  s.append(h('div', {class: 'notes'}, h('ul', {}, li.map(t => h('li', {text: t})))));
  return s;
}

/* ---------- assemble ---------- */
const app = $('#app'), nav = $('#nav');
const scenes = [['s1', 'Customers', sceneCustomers], ['s2', 'Route', sceneRoute], ['s3', 'Rider', sceneRider], ['s4', 'Noise ladder', sceneLadder]];
if (R.stress) scenes.push(['s5', 'Stress', sceneStress]);
if (R.replay) scenes.push(['s6', 'Replay', sceneReplay]);
scenes.push(['notes', 'Notes', sceneNotes]);
for (const [id, label, fn] of scenes) {
  const el = fn();
  app.append(el);
  nav.append(h('a', {href: '#' + id, text: label}));
}
requestAnimationFrame(redrawAll);
addEventListener('resize', redrawAll);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redrawAll);
const links = [...nav.querySelectorAll('a')];
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) links.forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + e.target.id)); }), {rootMargin: '-40% 0px -55% 0px'});
document.querySelectorAll('main section').forEach(sec => io.observe(sec));

/* ---------- "Play the demo" ---------- */
let token = 0;
async function playAll() {
  const my = ++token, play = $('#play'), stop = $('#stop');
  play.disabled = true; play.textContent = 'Playing…'; stop.hidden = false;
  for (const g of registry) {
    if (my !== token) break;
    g.el.classList.add('active');
    g.el.scrollIntoView({behavior: 'smooth', block: 'center'});
    if (g.onEnter) g.onEnter();
    await sleep(500);
    for (const f of g.files) { if (my !== token) break; await playClip(f); await sleep(220); }
    if (g.pause) await sleep(g.pause);
    g.el.classList.remove('active', 'anim');
    await sleep(250);
  }
  if (my === token) token++;
  registry.forEach(g => g.el.classList.remove('active', 'anim'));
  play.disabled = false; play.textContent = 'Play the demo'; stop.hidden = true;
}
$('#play').addEventListener('click', playAll);
$('#stop').addEventListener('click', () => { token++; for (const f in players) players[f].pause(); registry.forEach(g => g.el.classList.remove('active', 'anim')); $('#play').disabled = false; $('#play').textContent = 'Play the demo'; $('#stop').hidden = true; });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(gnani.HERE / "out" / "demo")
    path, missing = build(out)
    print(f"wrote {path}  ({path.stat().st_size // 1024} KB)")
    if missing:
        print("audio files named in the results but not found:", ", ".join(missing))
