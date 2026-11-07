"""Checkpoint flow: one expected landmark, voice in, prompts out. Pure logic (no API calls).

LISTEN -> (ACCEPT) confirmed
       -> (CONFIRM) yes/no read-back -> yes: confirmed, no: not found
       -> (ASK_AGAIN / MISMATCH) ask again, then yes/no on repeated conflict
       -> after max attempts: tap fallback -> found / not found / unconfirmed
A voice failure never counts against the landmark; only an explicit 'no' or tap does.
"""
from dataclasses import dataclass

from textutil import tokens
from verify import ACCEPT, ASK_AGAIN, CONFIRM, MISMATCH, verify

PROMPTS = {
    "hi-IN": {
        "next": "अगला: {p}।",
        "again": "दोबारा बोलिए।",
        "again_short": "कृपया फिर बोलिए।",
        "confirm": "{p}, सही है? बोलिए: हाँ, सही है। या: नहीं, गलत है।",
        "yn_again": "बोलिए: हाँ, सही है। या: नहीं, गलत है।",
        "tap": "बटन दबाइए: मिल गया, या नहीं मिला।",
        "done": "ठीक है।",
        "not_found": "समझ गया, नहीं मिला।",
    },
    "mr-IN": {
        "next": "पुढचे: {p}.",
        "again": "पुन्हा सांगा.",
        "again_short": "कृपया पुन्हा सांगा.",
        "confirm": "{p}, बरोबर? म्हणा: हो, बरोबर आहे. किंवा: नाही, चुकीचे आहे.",
        "yn_again": "म्हणा: हो, बरोबर आहे. किंवा: नाही, चुकीचे आहे.",
        "tap": "बटण दाबा: सापडले, किंवा सापडले नाही.",
        "done": "ठीक आहे.",
        "not_found": "समजले, सापडले नाही.",
    },
}
YES = {"हां", "जी", "ठीक", "सही", "हो", "होय", "बरोबर", "येस", "yes", "ok", "ओके", "सहि"}
UNSURE = {"पता", "मालूम", "माहीत", "माहित", "शायद", "कदाचित"}
NO = {"नहीं", "नही", "ना", "नाही", "नको", "गलत", "चूक", "चुकीचे", "no"}


def parse_yes_no(text):
    toks = set(tokens(text))
    if toks & UNSURE:
        return None
    y, n = bool(toks & YES), bool(toks & NO)
    if y and not n:
        return "yes"
    if n and not y:
        return "no"
    return None


@dataclass
class Action:
    kind: str    # SPEAK_NEXT ASK_AGAIN CONFIRM_YN CONFIRMED NOT_FOUND FALLBACK_TAP UNCONFIRMED
    text: str    # what Timbre should say ("" when nothing to say)
    reason: str = ""


class Checkpoint:
    def __init__(self, expected, lang="hi-IN", max_attempts=3):
        self.expected, self.lang, self.max_attempts = expected, lang, max_attempts
        self.p = PROMPTS[lang]
        self.state = "LISTEN"          # LISTEN AWAIT_YN AWAIT_TAP DONE
        self.status = None             # CONFIRMED NOT_FOUND UNCONFIRMED
        self.method = None             # voice yes tap
        self.attempts = 0
        self.conflicts = 0
        self.log = []
        self._final = None

    def prompt_next(self):
        return Action("SPEAK_NEXT", self.p["next"].format(p=self.expected))

    def _finish(self, status, method, kind, text, reason=""):
        self.state, self.status, self.method = "DONE", status, method
        self._final = Action(kind, text, reason)
        return self._final

    def _fail(self, reason, text_key):
        self.attempts += 1
        if self.attempts >= self.max_attempts:
            self.state = "AWAIT_TAP"
            return Action("FALLBACK_TAP", self.p["tap"], reason)
        text = self.p[text_key if self.attempts == 1 else "again_short"]
        return Action("ASK_AGAIN", text, reason)

    def hear(self, transcript):
        if self.state == "DONE":
            return self._final
        if self.state == "AWAIT_TAP":
            return Action("FALLBACK_TAP", self.p["tap"], "waiting_for_tap")

        if self.state == "AWAIT_YN":
            yn = parse_yes_no(transcript)
            self.log.append({"heard": transcript, "yn": yn})
            if yn == "yes":
                return self._finish("CONFIRMED", "yes", "CONFIRMED", self.p["done"])
            if yn == "no":
                return self._finish("NOT_FOUND", "yes", "NOT_FOUND", self.p["not_found"])
            self.attempts += 1
            if self.attempts >= self.max_attempts:
                self.state = "AWAIT_TAP"
                return Action("FALLBACK_TAP", self.p["tap"], "unclear_yes_no")
            return Action("CONFIRM_YN", self.p["yn_again"], "unclear_yes_no")

        v = verify(self.expected, transcript)
        self.log.append({"heard": transcript, "decision": v.decision, "reason": v.reason})
        if v.decision == ACCEPT:
            return self._finish("CONFIRMED", "voice", "CONFIRMED", self.p["done"], v.reason)
        if v.decision == CONFIRM:
            self.state = "AWAIT_YN"
            return Action("CONFIRM_YN", self.p["confirm"].format(p=self.expected), v.reason)
        if v.decision == MISMATCH:
            self.conflicts += 1
            if self.conflicts >= 2 and self.attempts + 1 < self.max_attempts:
                self.attempts += 1
                self.state = "AWAIT_YN"
                return Action("CONFIRM_YN", self.p["confirm"].format(p=self.expected), "repeated_" + v.reason)
            return self._fail(v.reason, "again")
        return self._fail(v.reason, "again")

    def tap(self, found):
        """found=True/False from the rider's button; None = skip (unconfirmed, delivery continues)."""
        if self.state == "DONE":
            return self._final
        if found is True:
            return self._finish("CONFIRMED", "tap", "CONFIRMED", self.p["done"])
        if found is False:
            return self._finish("NOT_FOUND", "tap", "NOT_FOUND", self.p["not_found"])
        return self._finish("UNCONFIRMED", "tap", "UNCONFIRMED", "", "skipped")
