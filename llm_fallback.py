"""Optional AI fallback for what the rules refuse. OFF unless LLM_BASE_URL is set (in the environment or in .env).

It talks to any OpenAI-style chat endpoint, such as `llama-server` running Gnani's open-weight Evon (see kaggle/serve/). The rules in
translate.py always go first. The AI is asked only when they could not translate a whole Hindi/Hinglish sentence, and its answer is used
only if guard.py finds that the details that change a route (left/right, negation, question, condition, colour, numbers) match the source.
Otherwise the rules' own result (a partial translation or a refusal) stands, so the AI can add coverage but not silently change a direction.

Not covered: who does what except for standing, coming and \"where\", and whether the whole sentence is faithful. A Kannada source is whatever Prisma wrote, so a misheard word is translated faithfully. The Kannada examples in the
prompt were written by me and have not been reviewed by a native speaker.

    LLM_BASE_URL=https://....trycloudflare.com      LLM_API_KEY=...        (the second only if the server was started with a key)
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

import guard
from textutil import tokens

HERE = Path(__file__).resolve().parent
NAME = "Evon"

RULES = ("Translate exactly. Do not add, remove or guess information. Keep numbers, colours and names. Keep conditions (if, when, until), "
         "negations (do not) and questions as they are. Say who does what: a statement about someone else stays a statement. "
         "Keep the people straight: in Hindi, \"aap\", \"tum\" and \"kahan ho\" (where are you) are about the OTHER person (you), while \"main\", \"mera\" and \"hoon\" are about the SPEAKER (I). "
         "If a part is unclear, write [unclear] there. Output only the translation, never the original.")
# (Hinglish, English, Kannada). Not from the test sentences. The Kannada lines were written by me and are NOT reviewed by a native speaker.
EXAMPLES = [("seedha aao phir left le lo", "Come straight, then turn left.", "ನೇರವಾಗಿ ಬನ್ನಿ, ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
            ("jab petrol pump dikhe tab ruk jana", "When you see the petrol pump, stop.", "ಪೆಟ್ರೋಲ್ ಬಂಕ್ ಕಾಣಿಸಿದಾಗ ನಿಲ್ಲಿ."),
            ("yahan ruko mat, aage jao", "Do not stop here, go ahead.", "ಇಲ್ಲಿ ನಿಲ್ಲಬೇಡಿ, ಮುಂದೆ ಹೋಗಿ."),
            ("क्या मैं यहाँ रुकूँ", "Should I stop here?", "ನಾನು ಇಲ್ಲಿ ನಿಲ್ಲಬೇಕೇ?"),
            ("aap kahan ho, main gate pe khada hoon", "Where are you? I am standing at the gate.", "ನೀವು ಎಲ್ಲಿದ್ದೀರಿ? ನಾನು ಗೇಟ್ ಹತ್ತಿರ ನಿಂತಿದ್ದೇನೆ.")]
# Kannada sources (the biker). (Kannada, Hindi, English). Written by me, NOT reviewed by a native speaker; not the test sentences.
EXAMPLES_KN = [("ನೀವು ಎಲ್ಲಿದ್ದೀರಿ, ನಾನು ಗೇಟ್ ಹತ್ತಿರ ನಿಂತಿದ್ದೇನೆ", "आप कहाँ हैं? मैं गेट के पास खड़ा हूँ।", "Where are you? I am standing near the gate."),
               ("ಬಲಕ್ಕೆ ತಿರುಗಿ, ನೇರವಾಗಿ ಬನ್ನಿ", "दाएं मुड़िए और सीधे आइए।", "Turn right and come straight."),
               ("ಐದು ನಿಮಿಷದಲ್ಲಿ ಬರುತ್ತೇನೆ", "मैं पाँच मिनट में आ रहा हूँ।", "I will come in five minutes."),
               ("ಇಲ್ಲಿ ನಿಲ್ಲಬೇಡಿ", "यहाँ मत रुकिए।", "Do not stop here."),
               ("ಕಟ್ಟಡ ಕಾಣಿಸಿದರೆ ನಿಲ್ಲಿ", "अगर बिल्डिंग दिखे तो रुकिए।", "If you see the building, stop."),
               ("ನಾನು ಇಲ್ಲಿ ನಿಲ್ಲಬೇಕೇ", "क्या मैं यहाँ रुकूँ?", "Should I stop here?")]
PEOPLE_KN = ("Keep the people straight: in Kannada, \"neevu\", \"ನೀವು\" and verbs ending -ದ್ದೀರಿ / -ದ್ದೀಯ are about the OTHER person (you), while \"ನಾನು\" and verbs ending "
             "-ದ್ದೇನೆ / -ದ್ದೀನಿ / -ತ್ತೇನೆ are about the SPEAKER (I). ")
INTRO = "You translate short phone-call messages between a customer and a delivery rider from {src} into {dst}. "
SYSTEM = {   # (source, target) -> system prompt
    ("hi-IN", "en"): "You translate short phone-call messages between a customer and a delivery rider from Hindi or Hinglish into English. " + RULES,
    ("hi-IN", "kn-IN"): ("You translate short phone-call messages between a customer and a delivery rider from Hindi or Hinglish into Kannada. "
                         "Always answer in Kannada script (ಕನ್ನಡ), even when the message is written in Roman letters. Never copy the message. " + RULES),
    ("kn-IN", "en"): "You translate short phone-call messages between a customer and a delivery rider from Kannada (as written by a speech recogniser) into English. " + PEOPLE_KN + RULES,
    ("kn-IN", "hi-IN"): ("You translate short phone-call messages between a customer and a delivery rider from Kannada (as written by a speech recogniser) into Hindi, "
                         "in Devanagari script. Use polite forms. Where the speaker's gender is unknown, avoid gendered verb forms if a neutral wording exists. "
                         "Never copy the message. " + PEOPLE_KN + RULES),
}
SHOT_COLUMN = {("hi-IN", "en"): (EXAMPLES, 1), ("hi-IN", "kn-IN"): (EXAMPLES, 2), ("kn-IN", "hi-IN"): (EXAMPLES_KN, 1), ("kn-IN", "en"): (EXAMPLES_KN, 2)}
SUPPORTED_DST = ("kn-IN", "en")                      # kept for the older callers: the targets for a Hindi source


def supported(src, dst):
    return (src, dst) in SYSTEM


def _dotenv(name):
    f = HERE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _urlopen_post(url, headers, body, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


class LlmFallback:
    def __init__(self, base_url, api_key="", post=_urlopen_post, timeout=25, clock=time.perf_counter, guard_on=True):
        base = base_url.rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base
        self.url, self.api_key, self.post, self.timeout, self.clock = f"{base}/v1/chat/completions", api_key, post, timeout, clock
        self.guard_on = guard_on                                 # off: an answer the check rejects is spoken anyway (and still labelled NOT checked)
        self.host = base.split("//")[-1]

    @classmethod
    def from_env(cls):
        url = os.environ.get("LLM_BASE_URL") or _dotenv("LLM_BASE_URL")
        guard = (os.environ.get("LLM_GUARD") or _dotenv("LLM_GUARD") or "on").strip().lower() not in ("off", "0", "no", "false")
        return cls(url, os.environ.get("LLM_API_KEY") or _dotenv("LLM_API_KEY"), guard_on=guard) if url else None

    def _chat(self, system, shots, text):
        msgs = [{"role": "system", "content": system}]
        for e in shots:
            msgs += [{"role": "user", "content": e[0]}, {"role": "assistant", "content": e[1]}]
        msgs.append({"role": "user", "content": text})
        headers = {"Content-Type": "application/json", "User-Agent": "landmark-chain/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps({"messages": msgs, "temperature": 0, "max_tokens": 180, "repeat_penalty": 1.1}).encode()
        out = self.post(self.url, headers, body, self.timeout)["choices"][0]["message"]["content"] or ""
        out = out.split("</think>")[-1] if "</think>" in out else out
        return re.split(r"<<|<\||\n\s*\n", out)[0].strip()      # the model sometimes carries on and invents the next message ("<<user>> ..."): keep only the answer

    def translate(self, text, dst, src="hi-IN"):
        """-> {status: ok|rejected|error, output, problems, seconds}. ok means the guard found the checked details matching, nothing more."""
        if not supported(src, dst):
            return {"status": "error", "output": "", "problems": [], "seconds": 0, "error": f"no AI route from {src} to {dst}"}
        t = self.clock()
        shots, col = SHOT_COLUMN[(src, dst)]
        try:
            out = self._chat(SYSTEM[(src, dst)], [(e[0], e[col]) for e in shots], text)
        except Exception as e:                                   # network, timeout, HTTP error, bad JSON: all just mean "no AI answer"
            return {"status": "error", "output": "", "problems": [], "seconds": round(self.clock() - t, 2), "error": f"{type(e).__name__}: {e}"[:200]}
        problems = guard.check(text, out, dst, src=src)
        empty = not out.strip()                                  # even with the check off, nothing is nothing
        return {"status": "rejected" if (problems and self.guard_on) or empty else "ok", "output": out, "problems": problems,
                "seconds": round(self.clock() - t, 2), "checked": self.guard_on}

    def meaning(self, text, src="hi-IN"):
        """An English gloss for the operator panel only. Not checked and never spoken. '' if it fails."""
        shots, col = SHOT_COLUMN[(src, "en")]
        try:
            return self._chat(SYSTEM[(src, "en")], [(e[0], e[col]) for e in shots], text)
        except Exception:
            return ""


class ReplayLlm:
    """Plays back AI answers recorded in an earlier real run, so a saved demo works without the model being up.

    It is NOT the model: it can only answer sentences that were in the recorded run, it says so (replayed=True on every answer, and the screen
    labels those turns "recorded answer"), and it still passes each answer through guard.py, so the check works the same as live.
    Used with `python live_call.py --replay-ai`."""
    name = NAME
    replay = True
    host = "recorded answers (not live)"

    def __init__(self, path, guard_on=True):
        self.guard_on, self.answers, self.gloss = guard_on, {}, {}
        for t in json.loads(Path(path).read_text(encoding="utf-8"))["turns"]:
            a = t.get("ai")
            if a and a.get("output"):
                key = (t["src"], t["dst"], " ".join(tokens(t["heard"])))
                self.answers[key] = a
                self.gloss[key] = (t.get("english") or "").replace(" (AI gloss, not checked)", "")

    def _key(self, text, src, dst):
        return (src, dst, " ".join(tokens(text)))

    def translate(self, text, dst, src="hi-IN"):
        a = self.answers.get(self._key(text, src, dst))
        if not a:
            return {"status": "error", "output": "", "problems": [], "seconds": 0, "error": "no recorded answer for this sentence (replay mode)", "replayed": True}
        problems = guard.check(text, a["output"], dst, src=src)
        return {"status": "rejected" if problems and self.guard_on else "ok", "output": a["output"], "problems": problems, "seconds": a.get("seconds", 0),
                "checked": self.guard_on, "replayed": True}

    def meaning(self, text, src="hi-IN"):
        g = next((v for k, v in self.gloss.items() if k[0] == src and k[2] == " ".join(tokens(text))), "")
        return g if g and not g.startswith("(") else ""
