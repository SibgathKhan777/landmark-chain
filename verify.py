"""Word-level verification of a heard transcript against the expected landmark.

Decisions:
  ACCEPT     every critical slot of the expected landmark was heard
  CONFIRM    nothing contradicts it, but some slots are missing -> ask a yes/no read-back
  MISMATCH   a slot was heard with a different value (other colour, other lane, other side...)
  ASK_AGAIN  empty, too short, or nothing matched -> never pick the 'nearest' candidate
"""
from dataclasses import dataclass, field

from extraction import CRITICAL, extract
from textutil import norm, tokens

ACCEPT, CONFIRM, MISMATCH, ASK_AGAIN = "ACCEPT", "CONFIRM", "MISMATCH", "ASK_AGAIN"
MIN_TOKENS = 2
# A transcript that says "not blue" must never count as "blue": negation downgrades an accept to a read-back.
NEGATIONS = {norm(w) for w in ["नहीं", "नही", "नाही", "नको", "गलत", "चूक", "चुकीचे", "not", "no", "nahi", "nahin"]}


@dataclass
class Verdict:
    decision: str
    reason: str
    matched: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)  # (slot, expected, heard)
    ambiguous: bool = False                        # a conflict where the expected value was also heard


def verify(expected_text, heard_text, min_tokens=MIN_TOKENS):
    heard_tokens = tokens(heard_text)
    if not heard_tokens:
        return Verdict(ASK_AGAIN, "empty")
    if len(heard_tokens) < min_tokens:
        return Verdict(ASK_AGAIN, "too_short")

    exp, got = extract(expected_text), extract(heard_text)
    v = Verdict(ACCEPT, "all_slots_matched")
    for slot in CRITICAL:
        e, g = exp[slot], got[slot]
        if not e:
            continue
        if e <= g and not (g - e):
            v.matched.append(slot)
        elif e <= g:                                   # expected value heard, but so was something else
            v.conflicts.append((slot, sorted(e), sorted(g)))
            v.ambiguous = True
        elif g and not (g & e):
            v.conflicts.append((slot, sorted(e), sorted(g)))
        else:
            v.missing.append(slot)

    if v.conflicts:
        v.decision = MISMATCH
        v.reason = ("ambiguous:" if v.ambiguous and not any(set(c[2]).isdisjoint(c[1]) for c in v.conflicts) else "conflict:") \
            + ",".join(c[0] for c in v.conflicts)
    elif v.missing and not v.matched:
        v.decision, v.reason = ASK_AGAIN, "nothing_matched"
    elif v.missing:
        v.decision, v.reason = CONFIRM, "missing:" + ",".join(v.missing)
    elif set(heard_tokens) & NEGATIONS:
        v.decision, v.reason = CONFIRM, "negation"
    return v
