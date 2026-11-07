"use strict";
/* Phone windows for the live call interpreter. mountPhone() builds one caller window. It subscribes to the server for ITS role only,
   so it can only ever receive audio and captions in its own language (or English, if that person chose it). */

const ROLES = {
  customer: { name: "Customer", person: "Arun", language: "Hindi", other: "biker", initial: "A" },
  biker: { name: "Biker", person: "Manju", language: "Kannada", other: "customer", initial: "M" },
};
const ICON = {
  phone: '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z"/></svg>',
  end: '<svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="transform:rotate(135deg)"><path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z"/></svg>',
  mic: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z"/></svg>',
};
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const secs = (ms) => (ms / 1000).toFixed(ms < 10000 ? 2 : 1) + " s";
const post = (url, data) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) }).then((r) => r.json());

/* ---------------------------------------------------------------- sound: one shared context, unlocked by the first click */
const Sound = (() => {
  let ctx = null, ringTimer = null, unlocked = false;
  const listeners = new Set();
  const ensure = () => { if (!ctx) { try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { ctx = null; } } return ctx; };
  const unlock = () => { const c = ensure(); if (c && c.state === "suspended") c.resume(); if (!unlocked) { unlocked = true; listeners.forEach((f) => f()); } };
  addEventListener("pointerdown", unlock, { capture: true });
  addEventListener("keydown", unlock, { capture: true });
  const beep = (when, f1, f2, dur) => {
    const c = ensure(); if (!c) return;
    const g = c.createGain(); g.gain.setValueAtTime(0.0001, when); g.gain.exponentialRampToValueAtTime(0.16, when + 0.03); g.gain.setValueAtTime(0.16, when + dur - 0.05); g.gain.exponentialRampToValueAtTime(0.0001, when + dur);
    g.connect(c.destination);
    [f1, f2].forEach((f) => { const o = c.createOscillator(); o.frequency.value = f; o.connect(g); o.start(when); o.stop(when + dur + 0.02); });
  };
  const ringOnce = () => { const c = ensure(); if (!c || c.state !== "running") return; const t = c.currentTime + 0.02; beep(t, 440, 480, 0.42); beep(t + 0.55, 440, 480, 0.42); };
  return {
    unlocked: () => unlocked, onUnlock: (f) => listeners.add(f),
    ring(on) { clearInterval(ringTimer); ringTimer = null; if (on) { ringOnce(); ringTimer = setInterval(ringOnce, 2600); } },
    chirp() { const c = ensure(); if (c && c.state === "running") beep(c.currentTime + 0.01, 880, 880, 0.12); },
  };
})();

/* ---------------------------------------------------------------- microphone -> 16 kHz mono WAV (push to talk) */
/* The microphone stays open while a call is connected (it only RECORDS while the button is held), so the first syllable is not lost to
   the delay of opening it, and it keeps 0.3 s from before the press. After the release it records 0.25 s more, so the last word is not cut. */
const Mic = (() => {
  const PRE = 0.3, TAIL_MS = 250;
  let ac = null, stream = null, proc = null, ring = [], ringLen = 0, rec = null, opening = null;
  async function open() {
    if (ac) return;
    if (!opening) opening = (async () => {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true } });
      ac = new (window.AudioContext || window.webkitAudioContext)();
      const src = ac.createMediaStreamSource(stream), mute = ac.createGain(); mute.gain.value = 0;
      proc = ac.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = (e) => {
        const d = new Float32Array(e.inputBuffer.getChannelData(0));
        if (rec) { rec.push(d); return; }
        ring.push(d); ringLen += d.length;
        while (ring.length > 1 && ringLen - ring[0].length >= PRE * ac.sampleRate) ringLen -= ring.shift().length;
      };
      src.connect(proc); proc.connect(mute); mute.connect(ac.destination);
    })();
    try { await opening; } finally { opening = null; }
  }
  return {
    async begin() { await open(); if (!rec) { rec = ring.slice(); ring = []; ringLen = 0; } },
    async end() {
      await new Promise((r) => setTimeout(r, TAIL_MS));
      const chunks = rec; rec = null; return chunks && ac ? encodeWav(chunks, ac.sampleRate, 16000) : new Blob([]);
    },
    close() { try { if (proc) proc.disconnect(); if (stream) stream.getTracks().forEach((t) => t.stop()); if (ac) ac.close(); } catch (e) { /* already closed */ } ac = stream = proc = null; ring = []; ringLen = 0; rec = null; },
  };
})();
function encodeWav(chunks, inRate, outRate) {
  let n = 0; chunks.forEach((c) => (n += c.length));
  const all = new Float32Array(n); let o = 0; chunks.forEach((c) => { all.set(c, o); o += c.length; });
  let peak = 0; for (let i = 0; i < all.length; i++) { const v = Math.abs(all[i]); if (v > peak) peak = v; }
  const gain = peak > 0.001 && peak < 0.4 ? Math.min(8, 0.6 / peak) : 1;            // a quiet microphone is brought up, a normal one is left alone
  const ratio = inRate / outRate, len = Math.floor(all.length / ratio), pcm = new Int16Array(len);
  for (let i = 0; i < len; i++) {
    const a = Math.floor(i * ratio), b = Math.min(all.length, Math.floor((i + 1) * ratio));
    let s = 0; for (let j = a; j < b; j++) s += all[j];
    const v = Math.max(-1, Math.min(1, gain * s / Math.max(1, b - a))); pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  const buf = new ArrayBuffer(44 + pcm.length * 2), dv = new DataView(buf);
  const w = (p, s) => [...s].forEach((ch, i) => dv.setUint8(p + i, ch.charCodeAt(0)));
  w(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVEfmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, outRate, true); dv.setUint32(28, outRate * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); w(36, "data"); dv.setUint32(40, pcm.length * 2, true);
  new Int16Array(buf, 44).set(pcm);
  return new Blob([buf], { type: "audio/wav" });
}

/* ---------------------------------------------------------------- one caller window */
function mountPhone(root, role, opts = {}) {
  const me = ROLES[role], other = ROLES[me.other];            // updated in place when the server says who speaks what in this call
  let mic = false, state = "idle", prefs = { customer: "native", biker: "native" }, connectedAt = 0, timer = null, scripted = false, playing = 0, queue = Promise.resolve();
  const win = el("section", "win"); win.dataset.role = role; win.setAttribute("aria-label", `${me.name} phone`);
  win.innerHTML = `
    <div class="titlebar"><span class="dots"><i></i><i></i><i></i></span><span class="t"></span></div>
    <div class="who"><div class="avatar">${me.initial}</div><div><div class="n">${me.person}</div><div class="s"></div></div><div class="timer" aria-live="off"></div></div>
    <div class="screen"></div>`;
  root.appendChild(win);
  const titleEl = win.querySelector(".titlebar .t"), sub = win.querySelector(".who .s"), timerEl = win.querySelector(".timer"), screen = win.querySelector(".screen");
  let caps = null, note = null, micBtn = null, hearSeg = null, soundNote = null;

  const hearLabel = () => (prefs[role] === "en" ? "English" : me.language);
  const refreshTitle = () => { titleEl.textContent = `${me.person} · ${me.name.toLowerCase()} · speaks ${me.language}`; };
  const applyRoles = (r) => { if (!r) return; for (const k of Object.keys(r)) if (ROLES[k]) Object.assign(ROLES[k], { language: r[k].language, person: r[k].person }); refreshTitle(); };
  refreshTitle();
  const refreshSub = () => { sub.textContent = state === "connected" ? `${me.name.toLowerCase()} · speaks ${me.language} · hears ${hearLabel()}` : `${me.name.toLowerCase()} · speaks ${me.language}`; };
  const tick = () => { const s = Math.floor((Date.now() - connectedAt) / 1000); timerEl.textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };

  function pop() { win.classList.remove("pop"); void win.offsetWidth; win.classList.add("pop"); }

  /* ------------ audio queue: this window only ever plays what the server sent to this role */
  function play(urls, label) {
    queue = queue.then(async () => {
      for (const u of urls) {
        const a = new Audio(u.url || u);
        playing++; setNote(label || "");
        try { await new Promise((res, rej) => { a.onended = res; a.onerror = res; a.play().catch(rej); }); }
        catch (e) { showSoundHint(); }
        playing--; if (!playing) setNote("");
      }
    });
    return queue;
  }
  function setNote(text) { if (!note) return; note.innerHTML = text ? `<span class="eq"><i></i><i></i><i></i><i></i></span><span></span>` : ""; if (text) note.lastChild.textContent = text; }
  function showSoundHint() { if (soundNote) soundNote.textContent = "Click anywhere in this window to turn the sound on."; }
  Sound.onUnlock(() => { if (soundNote) soundNote.textContent = ""; });

  /* ------------ screens */
  function render() {
    screen.innerHTML = ""; caps = note = micBtn = hearSeg = soundNote = null; refreshSub();
    clearInterval(timer); timerEl.textContent = "";
    Sound.ring(state === "ringing" && role === "biker");
    if (state !== "connected") Mic.close();                  // the microphone is only open during a connected call
    if (state === "idle" || state === "ended") {
      const box = el("div", "center-msg");
      if (role === "customer") {
        box.append(el("h2", null, state === "ended" ? "Call ended" : `Call ${other.person}`), el("div", null, `You speak ${me.language}. ${other.person} (the ${other.name.toLowerCase()}) hears ${other.language === "English" ? "English" : other.language + " or English"}.`));
        const b = el("button", "round green", ICON.phone); b.setAttribute("aria-label", "Call the biker");
        b.onclick = () => post("/api/call", { action: "start" }); box.append(b);
      } else {
        box.append(el("h2", null, state === "ended" ? "Call ended" : "Waiting for a call"), el("div", null, `You speak ${me.language}. The customer's words reach you in ${me.language} or English.`));
      }
      screen.append(box);
    } else if (state === "ringing") {
      const box = el("div", "center-msg");
      box.append(el("div", "ring", `<div class="avatar" style="background:${role === "biker" ? "#62adff" : "#b69cff"}">${other.initial}</div>`));
      if (role === "biker") {
        box.append(el("h2", null, "Incoming call"), el("div", null, `${other.person} (${other.name.toLowerCase()}) · speaks ${other.language}`));
        const row = el("div", "row");
        const no = el("div"), yes = el("div");
        const bn = el("button", "round red", ICON.end); bn.setAttribute("aria-label", "Decline"); bn.onclick = () => post("/api/call", { action: "end" });
        const by = el("button", "round green", ICON.phone); by.setAttribute("aria-label", "Answer"); by.onclick = () => post("/api/call", { action: "answer" });
        no.append(bn, el("span", null, "Decline")); yes.append(by, el("span", null, "Answer")); row.append(no, yes); box.append(row);
      } else {
        box.append(el("h2", null, `Calling ${other.person}…`), el("div", null, "ringing"));
        const b = el("button", "round red", ICON.end); b.setAttribute("aria-label", "Cancel"); b.onclick = () => post("/api/call", { action: "end" }); box.append(b);
      }
      screen.append(box);
    } else if (state === "connected") {
      connectedAt = connectedAt || Date.now(); tick(); timer = setInterval(tick, 1000);
      caps = el("div", "caps"); caps.setAttribute("aria-live", "polite"); note = el("div", "live-note");
      hearSeg = el("div", "hear", `Hear ${other.person} in`);
      const seg = el("div", "seg"); seg.setAttribute("role", "group");
      [["native", me.language], ["en", "English"]].forEach(([v, label]) => {
        const b = el("button", null, label); b.setAttribute("aria-pressed", String(prefs[role] === v));
        b.onclick = () => post("/api/prefs", { role, hear: v }); seg.append(b);
      });
      if (me.language !== "English") hearSeg.append(seg); else hearSeg.append(el("b", null, "English"));
      const dock = el("div", "dock");
      micBtn = el("button", "mic", ICON.mic + "<span>Hold to speak</span>");
      micBtn.disabled = scripted; micBtn.title = scripted ? "The scripted call is speaking for both people" : "Hold to speak. Your voice is sent to Gnani's API.";
      const end = el("button", "round red", ICON.end); end.style.cssText = "width:48px;height:48px;flex:none"; end.setAttribute("aria-label", "End call"); end.onclick = () => post("/api/call", { action: "end" });
      wireMic(micBtn); dock.append(micBtn, end);
      soundNote = el("div", "sound"); if (!Sound.unlocked()) showSoundHint();
      screen.append(caps, note, soundNote, hearSeg, dock);
    }
  }

  /* ------------ push to talk (your own microphone) */
  function wireMic(btn) {
    const label = btn.querySelector("span");
    const down = async (e) => {
      e.preventDefault(); if (btn.disabled || mic) return;
      mic = true; btn.classList.add("hot"); label.textContent = "Listening… release to send";
      try { await Mic.begin(); }
      catch (err) { mic = false; btn.classList.remove("hot"); label.textContent = "Microphone not available"; }
    };
    const up = async () => {
      if (!mic) return; mic = false; btn.classList.remove("hot"); label.textContent = "Sending…";
      const blob = await Mic.end(); label.textContent = "Hold to speak";
      if (blob.size < 6000) return;                                             // under ~0.2 s: ignore
      try {
        const r = await fetch(`/api/utterance?who=${role}`, { method: "POST", body: blob }); const j = await r.json();
        if (!r.ok) addCap("me note", "Not sent", j.error || "error");
      } catch (e) { addCap("me note", "Not sent", "could not reach the server"); }
    };
    btn.addEventListener("pointerdown", down); addEventListener("pointerup", up);
    btn.addEventListener("keydown", (e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) down(e); });
    btn.addEventListener("keyup", (e) => { if (e.key === " " || e.key === "Enter") up(); });
  }

  function addCap(cls, tag, text, chip, extra) {
    if (!caps) return null;
    const c = el("div", "cap " + cls), t = el("div", "tag"), x = el("div", "tx");
    t.append(document.createTextNode(tag)); if (chip) t.append(el("span", "chip " + chip, { translated: "translated", partial: "partly translated", untranslated: "not translated", silent: "heard nothing", ai: "AI translated, not fully checked", ai_unchecked: "AI translated, NOT checked", ai_replay: "AI translated, recorded answer" }[chip] || chip));
    x.textContent = text; c.append(t, x); if (extra) c.append(extra);
    caps.append(c); caps.scrollTop = caps.scrollHeight; return c;
  }

  /* ------------ events from the server (this role only) */
  const es = new EventSource(`/api/events?role=${role}`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "snapshot") {
      applyRoles(ev.roles); prefs = ev.prefs; scripted = !!ev.script_running;
      if (ev.state !== state) { state = ev.state; connectedAt = state === "connected" ? Date.now() : 0; render(); } else refreshSub();
    } else if (ev.type === "call") {
      applyRoles(ev.roles); const was = state; state = ev.state; connectedAt = state === "connected" ? Date.now() : 0; scripted = !!ev.script_running;
      if (state === "ringing") pop();
      if (state === "connected" && was === "ringing") { Sound.chirp(); pop(); }
      render();
    } else if (ev.type === "prefs") {
      prefs = ev.prefs; refreshSub();
      if (hearSeg) hearSeg.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(prefs[role] === (i ? "en" : "native"))));
    } else if (ev.type === "speaking") {                                  // scripted call: this person is "talking" (a synthetic voice)
      scripted = true; if (micBtn) micBtn.disabled = true;
      setNote("speaking (demo voice)"); if (ev.original) play([ev.original], "speaking (demo voice)");
    } else if (ev.type === "you_said") {
      const c = addCap("me" + (ev.status === "silent" ? " note" : ""), "You said", ev.text || "(nothing was heard)", ev.status === "translated" ? "" : ev.replayed ? "ai_replay" : ev.status);
      if (ev.notices && ev.notices.length) { addCap("me note", "Interpreter to you", ev.notices.map((n) => n.text).join(" ")); play(ev.notices, "interpreter"); }
    } else if (ev.type === "error") {
      addCap("me note", "Interpreter", ev.message);
    } else if (ev.type === "incoming") {
      const cls = ev.status === "partial" ? "them partial" : ev.status === "untranslated" ? "them note" : ev.status === "ai" || ev.status === "ai_unchecked" ? "them ai" : "them";
      addCap(cls, `Interpreter · ${ev.lang === "en" ? "English" : me.language}`, ev.text, ev.status === "translated" ? "" : ev.replayed ? "ai_replay" : ev.status);
      play(ev.speaks, "interpreter speaking");
    }
  };
  es.onerror = () => { /* the browser reconnects by itself and the server sends a fresh snapshot */ };
  render();
  return { win, role, destroy: () => es.close() };
}
