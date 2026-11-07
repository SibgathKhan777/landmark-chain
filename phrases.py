"""Render language-neutral landmark slots back into a Hindi or Marathi phrase.

The store keeps slots (TEMPLE + BEHIND + BLUE + GATE), so a Marathi rider can hear what a Hindi
customer said. Only the combinations in the tables below are supported; anything else returns None
and the caller falls back to the customer's own wording.
Property: extract(render(slots, lang)) gives the same slots back (tested).
"""

ANCHOR_HI = {"TEMPLE": "मंदिर", "MOSQUE": "मस्जिद", "SCHOOL": "स्कूल", "TANK": "पानी की टंकी",
             "POST_OFFICE": "पोस्ट ऑफिस", "PETROL_PUMP": "पेट्रोल पंप"}
REL_HI = {"BEHIND": "पीछे", "FRONT": "सामने", "NEAR": "पास", "AFTER": "बाद"}

# Marathi fuses the relation onto the noun; stems are written out per anchor.
ANCHOR_MR = {"TEMPLE": ("देवळा", "देवळाच्या"), "MOSQUE": ("मशिदी", "मशिदीच्या"), "SCHOOL": ("शाळे", "शाळेच्या"),
             "TANK": ("पाण्याच्या टाकी", "पाण्याच्या टाकीच्या"), "POST_OFFICE": ("पोस्ट ऑफिस", "पोस्ट ऑफिसच्या"),
             "PETROL_PUMP": ("पेट्रोल पंपा", "पेट्रोल पंपाच्या")}
REL_MR = {"FRONT": "समोर", "NEAR": "जवळ", "AFTER": "नंतर"}   # BEHIND is a separate word: "<anchor>च्या मागे"

COLOUR = {
    "hi-IN": {"m": {"BLUE": "नीला", "RED": "लाल", "GREEN": "हरा", "YELLOW": "पीला"},
              "f": {"BLUE": "नीली", "RED": "लाल", "GREEN": "हरी", "YELLOW": "पीली"}},
    "mr-IN": {"m": {"BLUE": "निळा", "RED": "लाल", "GREEN": "हिरवा", "YELLOW": "पिवळा"},
              "f": {"BLUE": "निळी", "RED": "लाल", "GREEN": "हिरवी", "YELLOW": "पिवळी"},
              "n": {"BLUE": "निळे", "RED": "लाल", "GREEN": "हिरवे", "YELLOW": "पिवळे"}},
}
ORDINAL = {
    "hi-IN": {"m": {"1": "पहला", "2": "दूसरा", "3": "तीसरा"}, "f": {"1": "पहली", "2": "दूसरी", "3": "तीसरी"}},
    "mr-IN": {"m": {"1": "पहिला", "2": "दुसरा", "3": "तिसरा"}, "f": {"1": "पहिली", "2": "दुसरी", "3": "तिसरी"},
              "n": {"1": "पहिले", "2": "दुसरे", "3": "तिसरे"}},
}
LANE_ORD_MR = {"1": "पहिल्या", "2": "दुसऱ्या", "3": "तिसऱ्या"}
TARGET = {   # canonical -> {lang: (word, gender)}
    "GATE": {"hi-IN": ("गेट", "m"), "mr-IN": ("गेट", "n")},
    "HOUSE": {"hi-IN": ("मकान", "m"), "mr-IN": ("घर", "n")},
    "SHOP": {"hi-IN": ("दुकान", "f"), "mr-IN": ("दुकान", "n")},
    "FLAT": {"hi-IN": ("फ्लैट", "m"), "mr-IN": ("फ्लॅट", "m")},
}
SIDE = {"hi-IN": {"LEFT": "बाएं तरफ", "RIGHT": "दाएं तरफ"}, "mr-IN": {"LEFT": "डाव्या बाजूला", "RIGHT": "उजव्या बाजूला"}}


def _one(slots, name):
    v = set(slots.get(name) or ())
    return next(iter(v)) if len(v) == 1 else None


def _anchor_phrase(anchor, rel, lang):
    if anchor not in ANCHOR_HI or rel not in REL_HI:
        return None
    if lang == "hi-IN":
        return f"{ANCHOR_HI[anchor]} के {REL_HI[rel]}"
    stem, gen = ANCHOR_MR[anchor]
    return f"{gen} मागे" if rel == "BEHIND" else f"{stem}{REL_MR[rel]}"


def render(slots, lang):
    """Slots (sets or lists) -> phrase in `lang`, or None when the combination is not supported."""
    if lang not in COLOUR:
        return None
    s = {k: set(v) for k, v in slots.items()}
    parts = []
    anchor, rel = _one(s, "anchor"), _one(s, "relation")
    if s.get("anchor") or s.get("relation"):
        ap = _anchor_phrase(anchor, rel, lang)
        if ap is None or len(s.get("relation", ())) != 1 or len(s.get("anchor", ())) != 1:
            return None
        parts.append(ap)

    colour, ordinal, side = _one(s, "colour"), _one(s, "ordinal"), _one(s, "side")
    for name, val in (("colour", colour), ("ordinal", ordinal), ("side", side)):
        if s.get(name) and val is None:
            return None
    target = s.get("target", set())

    if target == {"LANE", "HOUSE"}:                      # "second lane, green house"
        if not ordinal or side:
            return None
        word, gender = TARGET["HOUSE"][lang]
        col = COLOUR[lang][gender].get(colour) if colour else None
        if colour and col is None:
            return None
        if lang == "hi-IN":
            parts.append(f"{ORDINAL[lang]['f'][ordinal]} गली में" + (f" {col}" if col else "") + f" {word}")
        else:
            parts.append(f"{LANE_ORD_MR[ordinal]} गल्लीतले" + (f" {col}" if col else "") + f" {word}")
        return " ".join(parts)

    if len(target) > 1:
        return None
    word = gender = None
    if target:
        t = next(iter(target))
        if t not in TARGET:
            return None
        word, gender = TARGET[t][lang]
    if side:
        parts.append(SIDE[lang][side])
    if ordinal:
        if gender is None:
            return None
        parts.append(ORDINAL[lang][gender][ordinal])
    if colour:
        if gender is None or colour not in COLOUR[lang][gender]:
            return None
        parts.append(COLOUR[lang][gender][colour])
    if word:
        parts.append(word)
    return " ".join(parts) if parts else None
