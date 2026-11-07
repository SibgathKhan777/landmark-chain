"""Rule-based translation of landmark phrases between Hindi and Kannada. No LLM, no machine translation.

How it works: speech is turned into text by Prisma, the text is reduced to language-neutral slots (extraction.py), and the
slots are written out again in the other language from fixed tables below. So it can only say what the tables can say:
  * landmark phrases built from known anchors, relations, colours, lane numbers, sides and targets;
  * a closed phrasebook: yes, no, found it, could not find it, please repeat.
Everything else is NOT translated, and the interpreter says so out loud instead of guessing.

English is produced for on-screen meaning (subtitles) only; it is never spoken.
The Kannada wording was drafted without a native-speaker review. kannada_review.md lists every Kannada string this module can
produce so that a Kannada speaker can check it.
"""
from dataclasses import dataclass, field

import directions
from extraction import CRITICAL, cleaned_tokens, extract, matched_tokens, split_chain_segments
from textutil import norm, tokens

LANGS = ("hi-IN", "kn-IN", "en")

# ------------------------------------------------------------------------------------------------ Hindi
HI_ANCHOR = {"TEMPLE": "मंदिर", "MOSQUE": "मस्जिद", "SCHOOL": "स्कूल", "TANK": "पानी की टंकी", "POST_OFFICE": "पोस्ट ऑफिस",
             "PETROL_PUMP": "पेट्रोल पंप", "TREE": "पेड़", "BUS_STAND": "बस स्टैंड", "BANK": "बैंक", "HOSPITAL": "अस्पताल",
             "MARKET": "बाजार", "CHOWK": "चौक", "BRIDGE": "पुल", "TEA_STALL": "चाय की टपरी"}
HI_REL = {"BEHIND": "पीछे", "FRONT": "सामने", "NEAR": "पास", "AFTER": "बाद", "BELOW": "नीचे", "ABOVE": "ऊपर"}
HI_COLOUR = {"m": {"BLUE": "नीला", "RED": "लाल", "GREEN": "हरा", "YELLOW": "पीला", "WHITE": "सफेद", "BLACK": "काला", "PINK": "गुलाबी",
                   "ORANGE": "नारंगी", "BROWN": "भूरा"},
             "f": {"BLUE": "नीली", "RED": "लाल", "GREEN": "हरी", "YELLOW": "पीली", "WHITE": "सफेद", "BLACK": "काली", "PINK": "गुलाबी",
                   "ORANGE": "नारंगी", "BROWN": "भूरी"}}
HI_ORD = {"m": {"1": "पहला", "2": "दूसरा", "3": "तीसरा", "4": "चौथा", "5": "पांचवां"},
          "f": {"1": "पहली", "2": "दूसरी", "3": "तीसरी", "4": "चौथी", "5": "पांचवीं"}}
HI_SIDE = {"LEFT": "बाएं तरफ", "RIGHT": "दाएं तरफ"}
HI_TARGET = {"GATE": ("गेट", "m"), "HOUSE": ("मकान", "m"), "SHOP": ("दुकान", "f"), "LANE": ("गली", "f"), "FLAT": ("फ्लैट", "m"),
             "DOOR": ("दरवाजा", "m"), "BUILDING": ("बिल्डिंग", "f"), "FLOOR": ("मंजिल", "f")}

# ------------------------------------------------------------------------------------------------ Kannada
# Anchors are stored in the genitive ("of the temple"), which is what attaches to a relation.
KN_ANCHOR = {"TEMPLE": "ದೇವಸ್ಥಾನದ", "MOSQUE": "ಮಸೀದಿಯ", "SCHOOL": "ಶಾಲೆಯ", "TANK": "ಟ್ಯಾಂಕಿನ", "POST_OFFICE": "ಅಂಚೆ ಕಚೇರಿಯ",
             "PETROL_PUMP": "ಪೆಟ್ರೋಲ್ ಬಂಕ್‌ನ", "TREE": "ಮರದ", "BUS_STAND": "ಬಸ್ ನಿಲ್ದಾಣದ", "BANK": "ಬ್ಯಾಂಕಿನ", "HOSPITAL": "ಆಸ್ಪತ್ರೆಯ",
             "MARKET": "ಮಾರುಕಟ್ಟೆಯ", "CHOWK": "ಸರ್ಕಲ್‌ನ", "BRIDGE": "ಸೇತುವೆಯ", "TEA_STALL": "ಚಹಾ ಅಂಗಡಿಯ"}
KN_REL_ADV = {"BEHIND": "ಹಿಂದೆ", "FRONT": "ಎದುರು", "NEAR": "ಹತ್ತಿರ", "AFTER": "ನಂತರ", "BELOW": "ಕೆಳಗೆ", "ABOVE": "ಮೇಲೆ"}
KN_REL_ADJ = {"BEHIND": "ಹಿಂದಿನ", "FRONT": "ಎದುರಿನ", "NEAR": "ಹತ್ತಿರದ", "AFTER": "ನಂತರದ", "BELOW": "ಕೆಳಗಿನ", "ABOVE": "ಮೇಲಿನ"}
KN_COLOUR = {"BLUE": "ನೀಲಿ", "RED": "ಕೆಂಪು", "GREEN": "ಹಸಿರು", "YELLOW": "ಹಳದಿ", "WHITE": "ಬಿಳಿ", "BLACK": "ಕಪ್ಪು", "PINK": "ಗುಲಾಬಿ",
             "ORANGE": "ಕಿತ್ತಳೆ", "BROWN": "ಕಂದು"}
KN_ORD = {"1": "ಮೊದಲನೇ", "2": "ಎರಡನೇ", "3": "ಮೂರನೇ", "4": "ನಾಲ್ಕನೇ", "5": "ಐದನೇ"}
KN_SIDE_ADV = {"LEFT": "ಎಡಗಡೆ", "RIGHT": "ಬಲಗಡೆ"}
KN_SIDE_ADJ = {"LEFT": "ಎಡಗಡೆಯ", "RIGHT": "ಬಲಗಡೆಯ"}
KN_TARGET = {"GATE": "ಗೇಟ್", "HOUSE": "ಮನೆ", "SHOP": "ಅಂಗಡಿ", "LANE": "ಗಲ್ಲಿ", "FLAT": "ಫ್ಲಾಟ್", "DOOR": "ಬಾಗಿಲು", "BUILDING": "ಕಟ್ಟಡ",
             "FLOOR": "ಮಹಡಿ"}
KN_LANE_GEN = "ಗಲ್ಲಿಯ"

# ------------------------------------------------------------------------------------------------ English (subtitles)
EN_ANCHOR = {"TEMPLE": "temple", "MOSQUE": "mosque", "SCHOOL": "school", "TANK": "water tank", "POST_OFFICE": "post office",
             "PETROL_PUMP": "petrol pump", "TREE": "tree", "BUS_STAND": "bus stand", "BANK": "bank", "HOSPITAL": "hospital",
             "MARKET": "market", "CHOWK": "chowk (square)", "BRIDGE": "bridge", "TEA_STALL": "tea stall"}
EN_REL = {"BEHIND": "behind the {}", "FRONT": "in front of the {}", "NEAR": "near the {}", "AFTER": "after the {}",
          "BELOW": "below the {}", "ABOVE": "above the {}"}
EN_COLOUR = {k.upper(): k for k in ("blue", "red", "green", "yellow", "white", "black", "pink", "orange", "brown")}
EN_ORD = {"1": "first", "2": "second", "3": "third", "4": "fourth", "5": "fifth"}
EN_SIDE = {"LEFT": "on the left", "RIGHT": "on the right"}
EN_TARGET = {"GATE": "gate", "HOUSE": "house", "SHOP": "shop", "LANE": "lane", "FLAT": "flat", "DOOR": "door", "BUILDING": "building",
             "FLOOR": "floor"}


def _unpack(slots):
    """Slots as sets, or None when a slot holds more than one value (the phrase is ambiguous for a table lookup)."""
    s = {k: set(slots.get(k) or ()) for k in ("anchor", "relation", "colour", "ordinal", "side", "target")}
    if any(len(s[k]) > 1 for k in ("relation", "colour", "ordinal", "side")):
        return None
    return s


def _one(s, k):
    return next(iter(s[k])) if s[k] else None


def _anchor_name(table, anchors, hanuman):
    """Display name for the anchor set, or None if it cannot be written."""
    if anchors == {"HANUMAN", "TEMPLE"}:
        return hanuman
    if anchors == {"HANUMAN"}:
        return hanuman.split()[0] if " " in hanuman else hanuman
    if len(anchors) == 1:
        return table.get(next(iter(anchors)))
    return None


def render_hi(slots):
    s = _unpack(slots)
    if s is None:
        return None
    parts = []
    rel, ordinal, colour, side = _one(s, "relation"), _one(s, "ordinal"), _one(s, "colour"), _one(s, "side")
    if s["anchor"] or rel:
        name = _anchor_name(HI_ANCHOR, s["anchor"], "हनुमान मंदिर")
        if not name or rel not in HI_REL:
            return None
        parts.append(f"{name} के {HI_REL[rel]}")
    targets = s["target"]
    if targets == {"LANE", "HOUSE"}:
        if not ordinal or side or ordinal not in HI_ORD["f"] or (colour and colour not in HI_COLOUR["m"]):
            return None
        parts.append(f"{HI_ORD['f'][ordinal]} गली में" + (f" {HI_COLOUR['m'][colour]}" if colour else "") + " मकान")
        return " ".join(parts)
    if len(targets) > 1:
        return None
    word = gender = None
    if targets:
        t = next(iter(targets))
        if t not in HI_TARGET:
            return None
        word, gender = HI_TARGET[t]
    if side:
        parts.append(HI_SIDE[side])
    if ordinal:
        if gender is None or ordinal not in HI_ORD[gender]:
            return None
        parts.append(HI_ORD[gender][ordinal])
    if colour:
        if gender is None or colour not in HI_COLOUR[gender]:
            return None
        parts.append(HI_COLOUR[gender][colour])
    if word:
        parts.append(word)
    return " ".join(parts) if parts else None


def render_kn(slots):
    s = _unpack(slots)
    if s is None:
        return None
    rel, ordinal, colour, side = _one(s, "relation"), _one(s, "ordinal"), _one(s, "colour"), _one(s, "side")
    targets = s["target"]
    if len(targets) > 1 and targets != {"LANE", "HOUSE"}:
        return None
    has_noun = bool(targets)
    parts = []
    if s["anchor"] or rel:
        name = _anchor_name(KN_ANCHOR, s["anchor"], "ಹನುಮಾನ್ ದೇವಸ್ಥಾನದ")
        table = KN_REL_ADJ if has_noun else KN_REL_ADV
        if not name or rel not in table:
            return None
        parts.append(f"{name} {table[rel]}")
    if targets == {"LANE", "HOUSE"}:
        if not ordinal or side or ordinal not in KN_ORD or (colour and colour not in KN_COLOUR):
            return None
        parts.append(f"{KN_ORD[ordinal]} {KN_LANE_GEN}" + (f" {KN_COLOUR[colour]}" if colour else "") + " ಮನೆ")
        return " ".join(parts)
    if has_noun and next(iter(targets)) not in KN_TARGET:
        return None
    if side:
        parts.append((KN_SIDE_ADJ if has_noun else KN_SIDE_ADV)[side])
    if ordinal:
        if not has_noun or ordinal not in KN_ORD:
            return None
        parts.append(KN_ORD[ordinal])
    if colour:
        if not has_noun or colour not in KN_COLOUR:
            return None
        parts.append(KN_COLOUR[colour])
    if has_noun:
        parts.append(KN_TARGET[next(iter(targets))])
    return " ".join(parts) if parts else None


def render_en(slots):
    s = _unpack(slots)
    if s is None:
        return None
    rel, ordinal, colour, side = _one(s, "relation"), _one(s, "ordinal"), _one(s, "colour"), _one(s, "side")
    targets = s["target"]
    head = []
    if targets == {"LANE", "HOUSE"}:
        if not ordinal or side:
            return None
        head = [f"{EN_COLOUR.get(colour, '')} house in the {EN_ORD[ordinal]} lane".strip()] if ordinal in EN_ORD else []
        tail = []
    else:
        if len(targets) > 1:
            return None
        word = EN_TARGET.get(next(iter(targets))) if targets else None
        if targets and word is None:
            return None
        if ordinal:
            if ordinal not in EN_ORD or not word:
                return None
            head.append(EN_ORD[ordinal])
        if colour:
            if colour not in EN_COLOUR or not word:
                return None
            head.append(EN_COLOUR[colour])
        if word:
            head.append(word)
        tail = [EN_SIDE[side]] if side else []
    if s["anchor"] or rel:
        name = _anchor_name(EN_ANCHOR, s["anchor"], "Hanuman temple")
        if not name or rel not in EN_REL:
            return None
        tail.append(EN_REL[rel].format(name))
    out = " ".join([" ".join(head)] + tail).strip()
    return out or None


RENDER = {"hi-IN": render_hi, "kn-IN": render_kn, "en": render_en}


def render(slots, lang):
    """Slots to a phrase in `lang`, or None when the tables cannot write it."""
    return RENDER[lang](slots)


# ------------------------------------------------------------------------------------------------ phrasebook (closed list)
def _set(*words):
    return {norm(w) for w in words}


INTENT_WORDS = {
    "hi-IN": {"YES": _set("हाँ", "जी", "ठीक", "सही", "वही"), "NO": _set("नहीं", "नही", "गलत")},
    "en": {"YES": _set("yes", "yeah", "yep", "correct", "okay", "ok"), "NO": _set("no", "nope", "wrong")},
    "kn-IN": {"YES": _set("ಹೌದು", "ಸರಿ", "ಓಕೆ"), "NO": _set("ಇಲ್ಲ", "ತಪ್ಪು")},
}
INTENT_TEXT = {
    "hi-IN": {"YES": "हाँ, सही है", "NO": "नहीं, गलत है", "FOUND": "मिल गया", "NOT_FOUND": "नहीं मिला", "REPEAT": "कृपया दोबारा बोलिए"},
    "kn-IN": {"YES": "ಹೌದು, ಸರಿ", "NO": "ಇಲ್ಲ, ತಪ್ಪು", "FOUND": "ಸಿಕ್ಕಿತು", "NOT_FOUND": "ಸಿಗಲಿಲ್ಲ", "REPEAT": "ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ"},
    "en": {"YES": "yes, that is right", "NO": "no, that is wrong", "FOUND": "found it", "NOT_FOUND": "could not find it",
           "REPEAT": "please say it again"},
}


def intents(text, lang):
    """Closed-list intents in `text`, with the tokens they used. NOT_FOUND wins over NO and FOUND."""
    toks = tokens(text)
    ts = set(toks)
    used, found = set(), []
    if lang == "hi-IN":
        no = ts & INTENT_WORDS[lang]["NO"]
        mil = [t for t in toks if t.startswith(norm("मिल")) or t.startswith(norm("दिख"))]
        if no and mil:
            found.append("NOT_FOUND"); used |= no | set(mil)
        elif mil and ts & _set("गया", "गई", "गयी", "गए"):
            found.append("FOUND"); used |= set(mil) | (ts & _set("गया", "गई", "गयी", "गए"))
        elif ts & _set("पहुंच", "पहुँच") and ts & _set("गया", "गई", "गयी", "गए"):
            found.append("FOUND"); used |= ts & _set("पहुंच", "पहुँच", "गया", "गई", "गयी", "गए")
        if ts & _set("दोबारा"):
            found.append("REPEAT"); used |= ts & _set("दोबारा")
    elif lang == "en":
        negated = bool(ts & _set("not", "cannot", "cant", "t", "couldnt", "unable"))
        look = ts & _set("find", "found", "see", "seeing", "locate")
        if negated and look:
            found.append("NOT_FOUND"); used |= look | (ts & _set("not", "cannot", "cant", "t", "couldnt", "unable", "can", "could"))
        elif ts & _set("found", "reached", "arrived") and not negated:
            found.append("FOUND"); used |= ts & _set("found", "reached", "arrived")
        if ts & _set("again", "repeat"):
            found.append("REPEAT"); used |= ts & _set("again", "repeat")
    else:
        nf = ts & _set("ಸಿಗಲಿಲ್ಲ", "ಕಾಣುತ್ತಿಲ್ಲ", "ಕಾಣಿಸುತ್ತಿಲ್ಲ", "ಕಾಣಲಿಲ್ಲ")
        fd = ts & _set("ಸಿಕ್ಕಿತು", "ಸಿಕ್ಕಿದೆ", "ತಲುಪಿದೆ", "ತಲುಪಿದ್ದೇನೆ", "ಬಂದೆ", "ಬಂದಿದ್ದೇನೆ")
        if nf:
            found.append("NOT_FOUND"); used |= nf
        elif fd:
            found.append("FOUND"); used |= fd
        if ts & _set("ಇನ್ನೊಮ್ಮೆ", "ಮತ್ತೊಮ್ಮೆ"):
            found.append("REPEAT"); used |= ts & _set("ಇನ್ನೊಮ್ಮೆ", "ಮತ್ತೊಮ್ಮೆ")
    if "NOT_FOUND" not in found:
        yes, no = ts & INTENT_WORDS[lang]["YES"], ts & INTENT_WORDS[lang]["NO"]
        if yes and no:
            found.append("AMBIGUOUS"); used |= yes | no
        elif yes:
            found.append("YES"); used |= yes
        elif no:
            found.append("NO"); used |= no
    return found, used


# ------------------------------------------------------------------------------------------------ the interpreter
FILLERS = {
    "hi-IN": _set("भैया", "भाई", "सर", "जी", "ये", "यह", "वो", "वह", "वाला", "वाली", "वाले", "के", "की", "का", "में", "पर", "से", "है", "हैं",
                  "हो", "था", "रहा", "रही", "और", "फिर", "तरफ", "side", "bhaiya", "bhai", "ye", "yeh", "wo", "woh", "wala", "wali", "ke",
                  "ki", "ka", "me", "mein", "par", "se", "hai", "hain", "aur", "phir", "sir", "ji", "बस", "अच्छा", "तो", "ना", "ही", "भी", "को", "कृपया", "बोलिए", "बोलिये", "मैं", "main", "mai", "आप", "aap", "please", "plz", "पहले", "pehle", "pahle", "and", "एन्ड",
                  "vaala", "vala", "waala"),
    "en": _set("the", "a", "an", "is", "are", "am", "m", "s", "i", "you", "it", "that", "this", "there", "please", "sir", "hello", "hi", "then", "and", "so",
               "just", "now", "well", "at", "on", "in", "to", "of", "your", "my", "me", "will", "ll", "ahead", "for", "thanks", "thank"),
    "kn-IN": _set("ಅಣ್ಣ", "ಸರ್", "ಈ", "ಆ", "ಇದು", "ಅದು", "ಒಂದು", "ಇದೆ", "ಇರುವ", "ಇರುವುದು", "ಆಗಿದೆ", "ಅಲ್ಲಿ", "ಇಲ್ಲಿ", "ಮತ್ತು", "ಹಾಗೂ",
                  "ಇದೇ", "ಅದೇ", "ಬದಿಯ", "ಕಡೆ", "ಕಡೆಗೆ", "ಭಾಗದ", "ಭಾಗ", "ದಯವಿಟ್ಟು", "ಹೇಳಿ", "ನಾನು"),
}
# Words that are part of a multi-word landmark name ("water tank", "post office", "bus stand", "tea stall"). They carry no
# meaning on their own, but must not be reported as "not understood" when the landmark itself was recognised.
ANCHOR_WORDS = {
    "TANK": ["पानी", "पाण्याच्या"], "POST_OFFICE": ["ऑफिस", "ऑफीस", "कार्यालय", "ಕಚೇರಿ"], "BUS_STAND": ["बस", "ಬಸ್"],
    "TEA_STALL": ["चाय", "चहा"], "PETROL_PUMP": ["ಬಂಕ್", "बंक"],
}
NOTICE = {   # said to a person whose message could not be translated, and to the person who is waiting
    "hi-IN": {"speaker": "यह अनुवाद नहीं हो सका। कृपया लैंडमार्क बताइए।",
              "listener": "सामने वाले की बात अनुवाद नहीं हो सकी।", "partial": "बाकी बात अनुवाद नहीं हो सकी।"},
    "kn-IN": {"speaker": "ಇದನ್ನು ಅನುವಾದಿಸಲು ಆಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಗುರುತನ್ನು ಹೇಳಿ.",
              "listener": "ಇನ್ನೊಬ್ಬರ ಮಾತನ್ನು ಅನುವಾದಿಸಲು ಆಗಲಿಲ್ಲ.", "partial": "ಉಳಿದ ಮಾತನ್ನು ಅನುವಾದಿಸಲು ಆಗಲಿಲ್ಲ."},
    "en": {"speaker": "This could not be translated. Please say a landmark.", "listener": "The other person's message could not be translated.",
           "partial": "The rest of the message could not be translated."},
}
REASON_TEXT = {
    "no_known_words": "none of the words are in the landmark list or the phrasebook",
    "ambiguous": "it names two values at once (for example two colours), and a table cannot pick one",
    "negation": "it says what a landmark is NOT; the tables cannot express negation",
    "unsupported_combination": "the words are known but the tables cannot write this combination in the other language",
    "ambiguous_answer": "it contains both yes and no",
    "several_landmarks": "several landmarks in one phrase; say them one at a time",
    "question": "it is a question; the tables only write statements, so a question would be turned into an instruction",
    "conflict": "it turns both ways (right and left) and a table cannot pick one",
    "condition": "it says when or if to do something, and a translation without that would give the wrong instruction",
    "third_person": "it is about someone else, or about something already happening, and would be turned into an instruction",
    "distance": "it counts lanes, signals or metres, and the tables cannot write a distance",
}


@dataclass
class Result:
    status: str                    # translated | partial | untranslated
    src: str
    dst: str
    source_text: str
    output: str = ""               # what is spoken to the listener (empty when untranslated)
    english: str = ""              # on-screen meaning of the output
    reason: str = ""
    reason_text: str = ""
    untranslated: list = field(default_factory=list)   # words the tables did not understand (display only)
    intents: list = field(default_factory=list)
    landmarks: list = field(default_factory=list)
    notice_to_speaker: str = ""
    notice_to_listener: str = ""   # spoken after a partial translation, or alone when nothing could be translated
    clauses: list = field(default_factory=list)       # directions and plans recognised (directions.py)
    coverage: float = 1.0                              # share of the content words the rules understood (1.0 = all of them)


def _coverage(content_words, untranslated):
    """Share of the content words that the rules understood. Words in an unsupported segment, written "(a b c)", count one each."""
    left = sum(len(u.strip("()").split()) for u in untranslated)
    return round(max(0.0, 1 - left / max(1, content_words)), 3)


def _refuse(res, reason):
    res.status, res.reason, res.reason_text = "untranslated", reason, REASON_TEXT[reason]
    res.output = res.english = ""
    res.notice_to_speaker, res.notice_to_listener = NOTICE[res.src]["speaker"], NOTICE[res.dst]["listener"]
    return res


def translate(text, src, dst):
    """Translate one spoken message from `src` (hi-IN, kn-IN or en) to `dst` (hi-IN, kn-IN or en). Never guesses: it refuses when unsure."""
    res = Result("untranslated", src, dst, text)
    if src == "en":
        text = directions.clean_english(text)
    clauses, used_idx, toks, why = directions.parse(text, src)
    if not clauses:
        return _landmarks(text, src, dst, res)
    if why:
        return _refuse(res, why)
    spoken, shown = [], []
    for c in clauses:
        out, en = directions.render(c, dst), directions.render(c, "en")
        if out is None or en is None:
            return _refuse(res, "unsupported_combination")
        spoken.append(out); shown.append(en)
    rest = " ".join(t for i, t in enumerate(toks) if i not in used_idx)
    sub = _landmarks(rest, src, dst, Result("untranslated", src, dst, rest)) if rest else None
    res.clauses = [c["act"] for c in clauses]
    if sub is not None and sub.status == "untranslated" and sub.reason != "no_known_words":
        return _refuse(res, sub.reason)                 # for example a negation among the leftover words: do not half-translate
    if sub is not None and sub.status != "untranslated":
        spoken += [sub.output]; shown += [sub.english]
        res.landmarks, res.intents = sub.landmarks, sub.intents
    res.untranslated = sub.untranslated if sub is not None else []
    res.coverage = _coverage(len([t for t in toks if t not in FILLERS[src] and len(t) > 1 and not t.isdigit()]), res.untranslated)
    res.output, res.english = ", ".join(spoken), ", ".join(shown)
    res.status = "partial" if res.untranslated or (sub is not None and sub.status == "partial") else "translated"
    if res.status == "partial":
        res.reason, res.reason_text = "partial", "only the directions, plans and landmark words were translated"
        res.notice_to_listener = NOTICE[dst]["partial"]
    return res


def _landmarks(text, src, dst, res):
    """The landmark phrases and the closed phrasebook (no directions). The part of translate() that was here first."""
    found, used = intents(text, src)
    res.intents = [i for i in found if i != "AMBIGUOUS"]
    known = matched_tokens(text) | used
    for anchor in extract(text)["anchor"]:
        known |= {t for t in cleaned_tokens(text) if any(t.startswith(norm(m)) for m in ANCHOR_WORDS.get(anchor, ()))}
    res.untranslated = [t for t in cleaned_tokens(text) if t not in known and t not in FILLERS[src] and len(t) > 1 and not t.isdigit()]
    if "AMBIGUOUS" in found:
        return _refuse(res, "ambiguous_answer")

    segments = []
    for seg, slots in split_chain_segments(text):
        s = {k: set(v) for k, v in slots.items()}
        if any(len(s[k]) > 1 for k in ("colour", "ordinal", "side")):
            return _refuse(res, "ambiguous")
        if len(s["anchor"]) > 1 and s["anchor"] != {"HANUMAN", "TEMPLE"}:
            return _refuse(res, "several_landmarks")
        if len(s["relation"]) > 1:                    # for example "go straight from the bus stand": directions are not supported
            return _refuse(res, "unsupported_combination")
        segments.append((seg, slots))
    if segments and "NO" in res.intents:
        return _refuse(res, "negation")           # "not the blue gate" cannot be written from the tables

    parts, english, unsupported = [], [], []
    for seg, slots in segments:
        out, en = render(slots, dst), render(slots, "en")
        if out is None:
            unsupported.append(seg)
            continue
        parts.append(out)
        english.append(en or "")
        res.landmarks.append({k: sorted(v) for k, v in slots.items() if v})

    lead = [i for i in res.intents if i in ("YES", "NO", "REPEAT")]
    tail = [i for i in res.intents if i in ("FOUND", "NOT_FOUND")]
    out_parts = [INTENT_TEXT[dst][i] for i in lead] + parts + [INTENT_TEXT[dst][i] for i in tail]
    en_parts = [INTENT_TEXT["en"][i] for i in lead] + english + [INTENT_TEXT["en"][i] for i in tail]
    if not out_parts:
        return _refuse(res, "unsupported_combination" if unsupported else "no_known_words")

    if unsupported:
        res.untranslated += [f"({u})" for u in unsupported]
    res.coverage = _coverage(len([t for t in cleaned_tokens(text) if t not in FILLERS[src] and len(t) > 1 and not t.isdigit()]), res.untranslated)
    res.output, res.english = ", ".join(out_parts), ", ".join(en_parts)
    res.status = "partial" if res.untranslated else "translated"
    if res.status == "partial":
        res.reason, res.reason_text = "partial", "only the landmark words and phrasebook words were translated"
        res.notice_to_listener = NOTICE[dst]["partial"]
    return res


# What it cannot do, each with a real example. Tests check that every example is refused for the stated reason, so this
# list is verified behaviour and not a promise.
LIMITS = [
    ("Ordinary conversation", "भैया चाय पीकर आना", "hi-IN", "no_known_words"),
    ("Times, numbers and reasons", "मैं पांच मिनट में पहुंचूंगा", "hi-IN", "no_known_words"),
    ("Directions with a landmark to start from", "बस स्टैंड से सीधे जाकर दाएं मुड़िए", "hi-IN", "unsupported_combination"),
    ("Do-not instructions", "दाएं मत मुड़ना सीधे आ जाओ", "hi-IN", "negation"),
    ("Questions", "क्या सीधे आ जाऊं", "hi-IN", "question"),
    ("Two opposite turns", "राइट ले लो लेफ्ट ले लो", "hi-IN", "conflict"),
    ("What a landmark is NOT", "नीला गेट नहीं, लाल गेट", "hi-IN", "negation"),
    ("Two values at once (two colours)", "नीला लाल गेट", "hi-IN", "ambiguous"),
    ("Several landmarks in one breath", "मंदिर के पीछे मस्जिद के पास", "hi-IN", "several_landmarks"),
    ("A landmark it has never seen", "गुरुद्वारे के पीछे हरा दरवाजा", "hi-IN", "unsupported_combination"),
    ("The same, said in Kannada", "ನೀಲಿ ಗೇಟ್ ಅಲ್ಲ, ಇಲ್ಲ", "kn-IN", "negation"),
]


def vocabulary_counts():
    """How much the tables can write, counted from the tables themselves."""
    return {"landmark types": len(KN_ANCHOR) + 1, "relations": len(KN_REL_ADV), "colours": len(KN_COLOUR), "lane or floor numbers": len(KN_ORD),
            "sides": len(KN_SIDE_ADV), "things to point at": len(KN_TARGET), "phrasebook phrases": len(INTENT_TEXT["kn-IN"])}
