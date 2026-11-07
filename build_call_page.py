"""Build out/call/index.html from out/call/results.json: the two-person call, turn by turn.

Everything shown is real output of the run (Prisma transcripts, translations, audio). The "can translate" examples and the
"cannot translate" list are computed from translate.py at build time, so they cannot drift from what the code does.

    python call_demo.py && python build_call_page.py
"""
import json
import sys
from pathlib import Path

import gnani
import translate as T
from build_page import peaks, wav_files

EXAMPLES = [("दूसरी गली में हरा मकान", "hi-IN", "kn-IN"), ("पानी की टंकी के पास पीला मकान", "hi-IN", "kn-IN"),
            ("बैंक के ऊपर सफेद मकान", "hi-IN", "kn-IN"), ("ದೇವಸ್ಥಾನದ ಹಿಂದಿನ ನೀಲಿ ಗೇಟ್", "kn-IN", "hi-IN"),
            ("ಎಡಗಡೆಯ ಮೊದಲನೇ ಅಂಗಡಿ", "kn-IN", "hi-IN"), ("ಮರದ ಕೆಳಗೆ", "kn-IN", "hi-IN")]
LANG = {"hi-IN": "Hindi", "kn-IN": "Kannada"}


def capabilities():
    ex = []
    for text, src, dst in EXAMPLES:
        r = T.translate(text, src, dst)
        ex.append({"src": LANG[src], "text": text, "dst": LANG[dst], "output": r.output, "english": r.english, "status": r.status})
    limits = []
    for title, text, lang, reason in T.LIMITS:
        dst = "kn-IN" if lang == "hi-IN" else "hi-IN"
        r = T.translate(text, lang, dst)
        limits.append({"title": title, "lang": LANG[lang], "example": text, "status": r.status, "reason": r.reason_text,
                       "says": r.notice_to_speaker})
    return {"examples": ex, "limits": limits, "counts": T.vocabulary_counts(), "phrasebook": T.INTENT_TEXT}


def build(out_dir):
    out = Path(out_dir)
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    pk, dur, missing = {}, {}, []
    for name in sorted(wav_files(res)):
        path = out / name
        if not path.exists():
            missing.append(name)
            continue
        pk[name] = peaks(path)
        s, sr = gnani.read_wav(path.read_bytes())
        dur[name] = round(len(s) / sr, 2)
    data = json.dumps({"res": res, "peaks": pk, "dur": dur, "missing": missing, "cap": capabilities()}, ensure_ascii=False)
    html = TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))
    target = out / "index.html"
    target.write_text(html, encoding="utf-8")
    return target, missing


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landmark call interpreter</title>
<style>
:root{--bg:#f5f2ec;--surface:#fff;--ink:#1c1e22;--muted:#5b6370;--line:#e4dfd5;--accent:#c4501b;--accent-soft:#fbe9df;--wave:#c9c3b6;
--cust:#0f6b63;--cust-bg:#dff3ef;--bike:#9a4a12;--bike-bg:#fbe9d6;
--ok:#17724a;--ok-bg:#e3f4ea;--warn:#8a5a0a;--warn-bg:#fcf0d6;--bad:#a12b1f;--bad-bg:#fbe4e0;--info:#244f9e;--info-bg:#e4ecfa;
--shadow:0 1px 2px rgba(20,20,20,.05),0 8px 24px rgba(20,20,20,.06)}
@media (prefers-color-scheme:dark){:root{--bg:#0f1217;--surface:#171b22;--ink:#eef0f3;--muted:#9ba4b3;--line:#272d38;--accent:#ff8d5c;--accent-soft:#33211a;--wave:#3a4252;
--cust:#6fdccf;--cust-bg:#12302c;--bike:#ffb27a;--bike-bg:#3a2415;
--ok:#6fdca4;--ok-bg:#12301f;--warn:#f0c26a;--warn-bg:#352a0e;--bad:#ff9a8c;--bad-bg:#3a1713;--info:#8db4ff;--info-bg:#16264a;--shadow:none}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Inter",system-ui,-apple-system,"Segoe UI","Noto Sans Devanagari","Noto Sans Kannada","Kohinoor Devanagari","Kannada Sangam MN",sans-serif;padding-bottom:64px}
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
main{max-width:1160px;margin:0 auto;padding:0 24px}
.hero{padding:52px 0 18px}
.hero h1{font-size:clamp(28px,4.6vw,46px);line-height:1.12;margin:0 0 14px;letter-spacing:-.02em;max-width:19em}
.hero p{color:var(--muted);font-size:18px;max-width:44em;margin:0 0 10px}
section{padding:32px 0 8px;scroll-margin-top:84px}
.sh{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.num{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--ink);color:var(--bg);font-size:13px;font-weight:700;flex:none}
h2{font-size:24px;margin:0;letter-spacing:-.01em}
.lead{color:var(--muted);margin:2px 0 18px 40px;max-width:48em}
.turn{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin-bottom:16px;box-shadow:var(--shadow);transition:border-color .2s,box-shadow .2s}
.turn.active{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),var(--shadow)}
.th{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.th b{font-size:15px}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}
@media (max-width:900px){.cols{grid-template-columns:1fr}.top{flex-wrap:wrap;position:static}nav{margin-left:0}}
.col{border:1px solid var(--line);border-radius:14px;padding:12px 14px;min-width:0}
.col.mid{background:color-mix(in srgb,var(--surface) 70%,var(--bg))}
.cl{font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.chip{display:inline-flex;align-items:center;gap:5px;border-radius:99px;padding:2px 10px;font-size:12.5px;font-weight:600;white-space:nowrap}
.chip.ok{color:var(--ok);background:var(--ok-bg)}.chip.warn{color:var(--warn);background:var(--warn-bg)}.chip.bad{color:var(--bad);background:var(--bad-bg)}
.chip.info{color:var(--info);background:var(--info-bg)}.chip.mute{color:var(--muted);background:var(--line)}
.chip.cust{color:var(--cust);background:var(--cust-bg)}.chip.bike{color:var(--bike);background:var(--bike-bg)}
.lab{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:10px 0 2px}
.txt{font-size:19px;line-height:1.45;overflow-wrap:anywhere}
.big{font-size:22px;font-weight:600}
.en{color:var(--muted);font-size:14px;margin-top:2px}
.w.diff{background:var(--warn-bg);color:var(--warn);border-radius:4px;padding:0 3px}
.nu{display:inline-block;margin:2px 4px 2px 0;padding:1px 8px;border-radius:6px;border:1px dashed var(--warn);color:var(--warn);font-size:14px}
.wavebox{display:flex;align-items:center;gap:10px;margin:8px 0 4px}
.wavebox canvas{flex:1;height:40px;min-width:0;display:block}
.pbtn{flex:none;width:34px;height:34px;border-radius:50%;border:0;background:var(--accent);color:#fff;display:grid;place-items:center;padding:0}
.pbtn svg{width:13px;height:13px;fill:#fff}
.dur{font-size:12px;color:var(--muted);flex:none;width:34px;text-align:right}
.small{font-size:13px;color:var(--muted)}
.spoken{margin-top:8px;padding-top:8px;border-top:1px dashed var(--line)}
table{border-collapse:collapse;width:100%;font-size:15px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:8px 16px 12px;box-shadow:var(--shadow);overflow-x:auto}
.notes{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:6px 22px 14px}
.notes li{margin:9px 0}
.cap{position:fixed;left:0;right:0;bottom:0;z-index:6;background:var(--ink);color:var(--bg);text-align:center;font-size:13px;padding:9px 16px}
footer{padding:36px 0;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<header class="top">
  <div class="brand"><div class="logo"></div><div><b>Landmark call interpreter</b><small>Built on Gnani Prisma and Timbre</small></div></div>
  <nav id="nav" aria-label="Sections"></nav>
  <div style="display:flex;gap:8px;align-items:center"><button id="play" class="primary" aria-label="Play the whole call">Play the call</button><button id="stop" class="ghost" hidden>Stop</button></div>
</header>
<main>
  <div class="hero">
    <h1>The customer speaks Hindi. The biker hears Kannada.</h1>
    <p>An interpreter sits on the call. It understands landmark words (gate, second, on the right, behind the temple, blue...) and a few set phrases, and says them in the other person's language. Anything else it refuses out loud, so nobody is misled.</p>
    <p>Every transcript, translation and clip below is a real output of one run. The voices are synthetic and the noise is simulated.</p>
  </div>
  <div id="app"></div>
  <footer>Generated from <code>results.json</code> by <code>build_call_page.py</code>. Translation is table-based and rule-based: no language model and no machine translation. The Kannada wording was drafted without a native-speaker review.</footer>
</main>
<div class="cap">Synthetic voices and simulated noise. Transcripts by Gnani Prisma, speech by Gnani Timbre. Rule-based translation of landmark phrases only.</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const R = D.res, CAP = D.cap;
const LANG = {'hi-IN': 'Hindi', 'kn-IN': 'Kannada'};
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
function player(f) { return players[f] || (players[f] = new Audio(f)); }
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
function setProgress(f, p) { for (const w of (waves[f] || [])) { w.p = p; drawWave(w.c, D.peaks[f] || [], p); } }
function playClip(f) {
  return new Promise(res => {
    const a = player(f);
    for (const k in players) if (k !== f) players[k].pause();
    a.onended = () => { setProgress(f, 0); res(); };
    a.onerror = () => res();
    a.ontimeupdate = () => setProgress(f, a.duration ? a.currentTime / a.duration : 0);
    a.currentTime = 0;
    a.play().catch(() => res());
  });
}
function toggleClip(f) { const a = player(f); if (!a.paused) { a.pause(); a.currentTime = 0; setProgress(f, 0); return; } playClip(f); }
const ICON = '<svg viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5v11l9-5.5z"/></svg>';
function clip(f, label) {
  if (!f) return null;
  if (!D.peaks[f]) return h('div', {class: 'small', text: 'audio file missing: ' + f});
  const c = h('canvas', {'aria-hidden': 'true'});
  (waves[f] = waves[f] || []).push({c, p: 0});
  const b = h('button', {class: 'pbtn', 'aria-label': 'Play ' + label, onclick: () => toggleClip(f)});
  b.innerHTML = ICON;
  return h('div', {class: 'wavebox'}, b, c, h('span', {class: 'dur', text: (D.dur[f] || 0).toFixed(1) + 's'}));
}
const strip = w => w.replace(/[।,.?!]/g, '').toLowerCase();
function heardText(said, heard) {
  if (!heard) return h('span', {class: 'small', text: '(empty transcript)'});
  const set = new Set(said.split(/\s+/).map(strip));
  return h('span', {}, heard.split(/\s+/).filter(Boolean).map(w => h('span', {class: set.has(strip(w)) ? 'w' : 'w diff'}, w + ' ')));
}
const STATUS = {translated: ['Translated', 'ok', '✓'], partial: ['Partly translated', 'warn', '↻'], untranslated: ['Not translated', 'bad', '✕']};
function section(id, n, title, lead) {
  return h('section', {id}, h('div', {class: 'sh'}, h('span', {class: 'num', text: n}), h('h2', {text: title})), lead ? h('p', {class: 'lead', text: lead}) : null);
}
const registry = [];

/* ---------- the call ---------- */
function spokenBlock(items) {
  return items.map(s => h('div', {class: 'spoken'},
    h('div', {class: 'cl', text: (s.kind === 'notice' ? 'Interpreter says (notice)' : 'Interpreter says') + ' · ' + LANG[s.lang] + ' · voice ' + s.voice}),
    h('div', {class: 'txt', text: s.text}), clip(s.audio, 'interpreter')));
}
function sceneCall() {
  const s = section('call', '1', 'The call, turn by turn', 'Each turn: who speaks, what the interpreter does with it, and what the other person hears. Highlighted words are where Prisma\'s transcript differs from what was said.');
  for (const t of R.turns) {
    const p = R.people[t.who], q = R.people[t.who === 'customer' ? 'biker' : 'customer'];
    const [stLabel, stCls, stSym] = STATUS[t.status];
    const toSpeaker = t.spoken.filter(x => x.to === t.who), toListener = t.spoken.filter(x => x.to !== t.who);
    const mid = h('div', {class: 'col mid'}, h('div', {class: 'cl', text: 'Interpreter (rules, no AI model)'}),
      h('span', {class: 'chip ' + stCls, text: stSym + ' ' + stLabel}),
      t.output ? h('div', {style: 'margin-top:8px'}, h('div', {class: 'lab', text: 'Says in ' + LANG[t.dst]}), h('div', {class: 'txt big', text: t.output}), t.english ? h('div', {class: 'en', text: 'means: ' + t.english}) : null) : null,
      t.not_understood.length ? h('div', {style: 'margin-top:8px'}, h('div', {class: 'lab', text: 'Words it did not understand'}), t.not_understood.map(w => h('span', {class: 'nu', text: w}))) : null,
      t.status !== 'translated' ? h('div', {class: 'small', style: 'margin-top:8px', text: 'Why: ' + t.reason_text}) : null);
    const card = h('div', {class: 'turn'},
      h('div', {class: 'th'}, h('span', {class: 'chip ' + (t.who === 'customer' ? 'cust' : 'bike'), text: 'Turn ' + t.n + ' · ' + p.label + ' (' + p.language + ')'}),
        h('span', {class: 'small', text: t.note}), h('span', {class: 'chip mute', text: p.line})),
      h('div', {class: 'cols'},
        h('div', {class: 'col'}, h('div', {class: 'cl', text: p.label + ' says · ' + p.language + ' · voice ' + p.voice}), clip(t.said_audio, p.label + ' speech'),
          h('div', {class: 'lab', text: 'Said'}), h('div', {class: 'txt', text: t.said}),
          h('div', {class: 'lab', text: 'Prisma heard'}), h('div', {class: 'txt'}, heardText(t.said, t.heard)),
          spokenBlock(toSpeaker)),
        mid,
        h('div', {class: 'col'}, h('div', {class: 'cl', text: q.label + ' hears · ' + q.language}), spokenBlock(toListener))));
    s.append(card);
    registry.push({el: card, files: [t.said_audio].concat(t.spoken.map(x => x.audio))});
  }
  return s;
}

/* ---------- what it can and cannot do ---------- */
function sceneCan() {
  const c = CAP.counts;
  const s = section('can', '2', 'What it can translate',
    'Landmark phrases built from ' + Object.entries(c).map(([k, v]) => v + ' ' + k).join(', ') + '. The tables are fixed lists; the examples below are computed from them.');
  s.append(h('div', {class: 'card'}, h('table', {},
    h('thead', {}, h('tr', {}, ['From', 'Said', 'Becomes', 'Meaning'].map(x => h('th', {text: x})))),
    h('tbody', {}, CAP.examples.map(e => h('tr', {}, h('td', {text: e.src}), h('td', {text: e.text}), h('td', {class: 'big', text: e.output}), h('td', {text: e.english})))))));
  s.append(h('p', {class: 'small', style: 'margin:12px 0 0 0'}, 'Set phrases: ' + Object.keys(CAP.phrasebook['kn-IN']).map(k => CAP.phrasebook['hi-IN'][k] + ' ↔ ' + CAP.phrasebook['kn-IN'][k]).join(' · ')));
  return s;
}
function sceneCannot() {
  const s = section('cannot', '3', 'What it cannot translate', 'In each case it says so, in the speaker\'s language, and tells the other person that something was not translated. It does not guess.');
  s.append(h('div', {class: 'card'}, h('table', {},
    h('thead', {}, h('tr', {}, ['Cannot do', 'Example (each one is tested)', 'Why'].map(x => h('th', {text: x})))),
    h('tbody', {}, CAP.limits.map(l => h('tr', {}, h('td', {text: l.title}), h('td', {text: l.example + '  (' + l.lang + ')'}), h('td', {text: l.reason})))))));
  return s;
}
function sceneNotes() {
  const n = R.turns.length, tr = R.turns.filter(t => t.status === 'translated').length, pa = R.turns.filter(t => t.status === 'partial').length, un = R.turns.filter(t => t.status === 'untranslated').length;
  const li = [
    n + ' turns: ' + tr + ' fully translated, ' + pa + ' partly translated, ' + un + ' refused.',
    'All voices are Gnani Timbre output, so no real person spoke. The customer\'s line has simulated phone noise, the biker\'s has simulated bike noise (engine hum plus babble from other synthetic voices). The interpreter\'s own speech is clean.',
    'The Kannada wording is drafted from word tables without a native-speaker review. In a clean-audio check, every phrase the tables can write survived Timbre speaking it and Prisma transcribing it with the same meaning, but that does not prove it sounds natural.',
    'Translation is a table lookup on landmark words. Anything outside the tables, including numbers, times, names, directions and "not the blue gate", is not translated.',
    'This is a scripted demo, not a live phone call. It has not been tried with real people, phones or traffic.',
  ];
  if (D.missing && D.missing.length) li.push('Missing audio files: ' + D.missing.join(', '));
  const s = h('section', {id: 'notes'}, h('div', {class: 'sh'}, h('span', {class: 'num', text: '!'}), h('h2', {text: 'What this run does and does not show'})));
  s.append(h('div', {class: 'notes'}, h('ul', {}, li.map(t => h('li', {text: t})))));
  return s;
}

const app = $('#app'), nav = $('#nav');
for (const [id, label, fn] of [['call', 'The call', sceneCall], ['can', 'Can', sceneCan], ['cannot', 'Cannot', sceneCannot], ['notes', 'Notes', sceneNotes]]) {
  app.append(fn()); nav.append(h('a', {href: '#' + id, text: label}));
}
requestAnimationFrame(redrawAll);
addEventListener('resize', redrawAll);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redrawAll);
const links = [...nav.querySelectorAll('a')];
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) links.forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + e.target.id)); }), {rootMargin: '-40% 0px -55% 0px'});
document.querySelectorAll('main section').forEach(sec => io.observe(sec));

let token = 0;
async function playAll() {
  const my = ++token, play = $('#play'), stop = $('#stop');
  play.disabled = true; play.textContent = 'Playing…'; stop.hidden = false;
  for (const g of registry) {
    if (my !== token) break;
    g.el.classList.add('active');
    g.el.scrollIntoView({behavior: 'smooth', block: 'center'});
    await sleep(500);
    for (const f of g.files) { if (my !== token) break; await playClip(f); await sleep(220); }
    g.el.classList.remove('active');
    await sleep(300);
  }
  if (my === token) token++;
  registry.forEach(g => g.el.classList.remove('active'));
  play.disabled = false; play.textContent = 'Play the call'; stop.hidden = true;
}
$('#play').addEventListener('click', playAll);
$('#stop').addEventListener('click', () => { token++; for (const f in players) players[f].pause(); registry.forEach(g => g.el.classList.remove('active')); $('#play').disabled = false; $('#play').textContent = 'Play the call'; $('#stop').hidden = true; });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(gnani.HERE / "out" / "call")
    path, missing = build(out)
    print(f"wrote {path}  ({path.stat().st_size // 1024} KB)")
    if missing:
        print("audio files named in the results but not found:", ", ".join(missing))
