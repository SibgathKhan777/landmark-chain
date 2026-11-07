"""Rule-based landmark slot extraction for Hindi and Marathi. No LLM, no network.

A landmark phrase is reduced to slots:
  anchor    what the landmark is (temple, mosque, tank, ...)
  relation  how the place relates to it (behind, in front of, after, ...)
  colour, ordinal (1st/2nd lane), side (left/right)   <- the words that tell look-alikes apart
  target    what is being located (gate, house, shop, lane, ...); not used for verification,
            because the tail of a phrase is the least reliable part of the transcript.

Marathi attaches suffixes and relations to nouns (देवळासमोर = temple + in front), so each lexicon
entry is matched as a prefix, an exact token, or a substring ("inside").
"""
from textutil import norm, tokens

SLOTS = ("anchor", "relation", "colour", "ordinal", "side", "target")
CRITICAL = ("anchor", "relation", "colour", "ordinal", "side")


def _e(canon, stems, mode="prefix"):
    return canon, [norm(s) for s in stems], mode


def _x(canon, stem, mode):
    return canon, [norm(stem)], mode


LEX = {
    "anchor": [
        _e("TEMPLE", ["मंदिर", "देवळ", "देऊळ"]),
        _e("MOSQUE", ["मस्जिद", "मशिद", "मशीद"]),
        _e("SCHOOL", ["स्कूल", "शाळ"]),
        _e("PETROL_PUMP", ["पेट्रोल", "पंप"]),
        _e("TREE", ["पीपल", "वड", "झाड", "पेड"]),
        _e("TANK", ["टंकी", "टाक"]),
        _e("BUS_STAND", ["स्टैंड", "स्टँड"]),
        _e("POST_OFFICE", ["पोस्ट"]),
        _e("HANUMAN", ["हनुमान", "मारुती"]),
        _e("BANK", ["बैंक", "बँक"]),
        _e("HOSPITAL", ["अस्पताल", "हॉस्पिटल", "दवाखान", "रुग्णालय"]),
        _e("MARKET", ["बाजार", "मार्केट", "मंडई"]),
        _e("CHOWK", ["चौक"]),
        _e("BRIDGE", ["पुला", "पूला"]), _x("BRIDGE", "पुल", "exact"), _x("BRIDGE", "पूल", "exact"),
        _e("TEA_STALL", ["टपरी", "चायवाल", "चहावाल"]),
        _e("POLE", ["खंब", "खांब"]),
    ],
    "relation": [
        _x("BEHIND", "पीछे", "exact"), _x("BEHIND", "मागे", "exact"), _x("BEHIND", "मागे", "suffix"),   # झाडामागे
        _x("FRONT", "सामने", "exact"), _x("FRONT", "समोर", "inside"),
        _x("NEAR", "पास", "exact"), _x("NEAR", "जवळ", "inside"),
        _x("NEAR", "शेजारी", "prefix"), _x("NEAR", "बगल", "prefix"),
        _x("AFTER", "बाद", "exact"), _x("AFTER", "नंतर", "inside"),
        _x("BELOW", "नीचे", "exact"), _x("BELOW", "खाली", "inside"),
        _x("ABOVE", "ऊपर", "exact"), _x("ABOVE", "वर", "exact"), _x("ABOVE", "वरच", "prefix"),
        _x("FROM", "पासून", "inside"), _x("FROM", "से", "exact"),
        _x("STRAIGHT", "सीधे", "prefix"), _x("STRAIGHT", "सरळ", "prefix"),
    ],
    "colour": [
        _e("BLUE", ["नील", "निळ"]), _e("RED", ["लाल"]),
        _e("GREEN", ["हरा", "हरे", "हरी", "हिरव"]), _e("YELLOW", ["पील", "पिवळ"]),
        _e("WHITE", ["सफेद", "सफेद", "पांढर", "पाढर"]), _e("PINK", ["गुलाबी"]),
        _e("ORANGE", ["नारंगी", "केशरी", "भगवा"]), _e("BROWN", ["भूरा", "भूरी", "तपकिरी"]),
        _e("BLACK", ["काला", "काली", "काले", "काळा", "काळी", "काळे", "काळ्या"], "exact"),
    ],
    "ordinal": [
        _e("1", ["पहल", "पहिल"]), _e("2", ["दूसर", "दुसर"]), _e("3", ["तीसर", "तिसर"]),
        _e("4", ["चौथ"]), _e("5", ["पांचव", "पाचव"]),
    ],
    "side": [
        _e("LEFT", ["बाए", "बाई", "बायी", "बाय", "डाव"]), _e("RIGHT", ["दाए", "दाई", "दायी", "दाय", "उजव"]),
    ],
    "target": [
        _e("GATE", ["गेट"]), _e("HOUSE", ["मकान", "घर"]), _e("SHOP", ["दुकान"]),
        _e("LANE", ["गली", "गल्ली"]), _e("FLAT", ["फ्लैट", "फ्लॅट", "फ्लेट"]), _e("DOOR", ["दरवाज"]),
        _e("BUILDING", ["बिल्डिंग", "इमारत"]), _e("FLOOR", ["मंजिल", "मजल"]),
    ],
}


# ---- Kannada (ಕನ್ನಡ). Prefix stems without the trailing virama so that inflected forms match (ಟ್ಯಾಂಕ್, ಟ್ಯಾಂಕಿನ).
# Drafted without a native-speaker review: see kannada_review.md.
LEX["anchor"] += [
    _e("TEMPLE", ["ದೇವಸ್ಥಾನ", "ದೇವಾಲಯ", "ಗುಡಿ"]), _e("MOSQUE", ["ಮಸೀದಿ"]), _e("SCHOOL", ["ಶಾಲೆ"]), _e("TANK", ["ಟ್ಯಾಂಕ"]),
    _e("POST_OFFICE", ["ಅಂಚೆ", "ಪೋಸ್ಟ"]), _e("PETROL_PUMP", ["ಪೆಟ್ರೋಲ"]), _e("TREE", ["ಮರದ"]), _x("TREE", "ಮರ", "exact"),
    _e("BUS_STAND", ["ಸ್ಟ್ಯಾಂಡ", "ನಿಲ್ದಾಣ"]), _e("BANK", ["ಬ್ಯಾಂಕ"]), _e("HOSPITAL", ["ಆಸ್ಪತ್ರೆ"]), _e("MARKET", ["ಮಾರುಕಟ್ಟೆ"]),
    _e("CHOWK", ["ಸರ್ಕಲ", "ಚೌಕ"]), _e("BRIDGE", ["ಸೇತುವೆ"]), _e("TEA_STALL", ["ಚಹಾ"]), _e("HANUMAN", ["ಹನುಮ"]),
]
LEX["relation"] += [
    _e("BEHIND", ["ಹಿಂದ"]), _e("FRONT", ["ಎದುರ", "ಮುಂದ"]), _e("NEAR", ["ಹತ್ತಿರ", "ಪಕ್ಕ"]), _e("AFTER", ["ನಂತರ", "ಆಮೇಲ"]),
    _e("BELOW", ["ಕೆಳಗ"]), _e("ABOVE", ["ಮೇಲ"]), _e("STRAIGHT", ["ನೇರ"]),
]
LEX["colour"] += [
    _e("BLUE", ["ನೀಲ"]), _e("RED", ["ಕೆಂಪ"]), _e("GREEN", ["ಹಸಿರ"]), _e("YELLOW", ["ಹಳದಿ"]), _e("WHITE", ["ಬಿಳಿ"]),
    _e("BLACK", ["ಕಪ್ಪ"]), _e("PINK", ["ಗುಲಾಬಿ"]), _e("ORANGE", ["ಕಿತ್ತಳೆ"]), _e("BROWN", ["ಕಂದು"]),
]
LEX["ordinal"] += [
    _e("1", ["ಮೊದಲ"]), _e("2", ["ಎರಡನೇ", "ಎರಡನೆಯ"]), _e("3", ["ಮೂರನೇ", "ಮೂರನೆಯ"]),
    _e("4", ["ನಾಲ್ಕನೇ", "ನಾಲ್ಕನೆಯ"]), _e("5", ["ಐದನೇ", "ಐದನೆಯ"]),
]
LEX["side"] += [_e("LEFT", ["ಎಡ"]), _e("RIGHT", ["ಬಲ"])]
LEX["target"] += [
    _e("GATE", ["ಗೇಟ"]), _e("HOUSE", ["ಮನೆ"]), _e("SHOP", ["ಅಂಗಡಿ"]), _e("LANE", ["ಗಲ್ಲಿ"]), _e("FLAT", ["ಫ್ಲಾಟ"]),
    _e("DOOR", ["ಬಾಗಿಲ"]), _e("BUILDING", ["ಕಟ್ಟಡ"]), _e("FLOOR", ["ಮಹಡಿ"]),
]

# Words that merely start like a lexicon entry: names, foods, everyday nouns. Never matched.
STOP = {norm(w) for w in [
    "हरीश", "हरेक", "हरामी", "लालबाग", "लालच", "लालू", "लालजी", "नीलेश", "नीलम", "नीलकंठ", "पहलवान", "पहल",
    "पेड़ा", "पेडा", "वडा", "वडापाव", "वडे", "झाडू", "पोस्टर", "बाई", "दाई", "बायको", "बाईक", "बाइक",
    "चौकी", "चौकीदार", "पुलिस", "पुलाव",
]}
# Place names that contain a colour word.
PLACE_NAMES = [norm(p) for p in ["लाल बाग", "लाल किला", "लाल महल", "लाल कुआं"]]

# Roman-script Hinglish (Prisma returns Latin script for en-IN). Exact tokens only.
_LATIN = {
    "colour": {"BLUE": "neela neeli neele nila nili blue", "RED": "laal lal laala red", "GREEN": "hara hari hare green",
               "YELLOW": "peela peeli peele pila pili yellow", "WHITE": "safed safaid white", "BLACK": "kala kaala kali kaali kale black",
               "PINK": "gulabi pink"},
    "relation": {"BEHIND": "peeche piche pichhe behind", "FRONT": "saamne samne front", "NEAR": "paas pas near",
                 "AFTER": "baad bad after", "BELOW": "neeche niche below", "ABOVE": "upar oopar above", "STRAIGHT": "seedha sidha straight"},
    "anchor": {"TEMPLE": "mandir temple", "MOSQUE": "masjid mosque", "SCHOOL": "school", "TANK": "tanki tank",
               "POST_OFFICE": "post", "PETROL_PUMP": "petrol", "TREE": "ped peepal tree", "BUS_STAND": "stand",
               "BANK": "bank", "HOSPITAL": "hospital", "MARKET": "market bazaar", "CHOWK": "chowk", "BRIDGE": "pul bridge",
               "HANUMAN": "hanuman maruti"},
    "ordinal": {"1": "pehli pehla pehle first", "2": "doosri doosra doosre dusri dusra second", "3": "teesri teesra teesre tisri third"},
    "side": {"LEFT": "left baayen bayen baayein baayi baai bayi", "RIGHT": "right daayen dayen daayein daayi daai dayi dahina dahine"},
    "target": {"GATE": "gate gaet", "HOUSE": "ghar makaan makan house", "SHOP": "dukaan dukan shop",
               "LANE": "gali lane", "FLAT": "flat", "BUILDING": "building bilding"},
}
LATIN = {slot: {canon: set(words.split()) for canon, words in d.items()} for slot, d in _LATIN.items()}


def _hit(token, stems, mode):
    for st in stems:
        if mode == "prefix" and token.startswith(st):
            return True
        if mode == "exact" and token == st:
            return True
        if mode == "inside" and st in token:
            return True
        if mode == "suffix" and token.endswith(st) and len(token) > len(st):
            return True
    return False


# Multi-word landmark names that contain a word for something else ("tea shop" contains "shop").
# (Only the Kannada alias exists because the call demo needs it. A Hindi "tea shop" alias was removed on purpose: it also
# fixed a phrase in evaluation set C, which must stay untouched by tuning.)
PHRASE_ALIASES = [(norm("ಚಹಾ ಅಂಗಡಿ"), norm("ಚಹಾ"))]


def cleaned_tokens(text):
    """Tokens after normalising, dropping place names that contain a colour word and folding multi-word names."""
    cleaned = norm(text)
    for place in PLACE_NAMES:
        cleaned = cleaned.replace(place, " ")
    for long_form, short_form in PHRASE_ALIASES:
        cleaned = cleaned.replace(long_form, short_form)
    return cleaned.split()


def _scan(text):
    """Yield (token, slot, canonical value) for every lexicon hit."""
    for tok in cleaned_tokens(text):
        if tok in STOP:
            continue
        for slot, entries in LEX.items():
            for canon, stems, mode in entries:
                if _hit(tok, stems, mode):
                    yield tok, slot, canon
        for slot, by_canon in LATIN.items():
            for canon, words in by_canon.items():
                if tok in words:
                    yield tok, slot, canon


def extract(text):
    """Return {slot: frozenset of canonical values} for a phrase."""
    out = {s: set() for s in SLOTS}
    for _tok, slot, canon in _scan(text):
        out[slot].add(canon)
    return {k: frozenset(v) for k, v in out.items()}


def matched_tokens(text):
    """The words of `text` that the lexicon recognised (used to show what was NOT understood)."""
    return {tok for tok, _slot, _canon in _scan(text)}


_SEPARATORS = {"फिर", "आगे", "मग", "त्यानंतर", "उसके"}


def split_chain_segments(text):
    """Split a longer description into ordered landmark steps: [(segment_text, slots), ...].

    Splits on commas, danda and separator words; keeps only segments that carry a critical slot.
    """
    for ch in ("।", ",", ";"):
        text = text.replace(ch, "|")
    segs, cur = [], []
    for part in text.split("|"):
        for tok in part.split():
            if norm(tok) in _SEPARATORS:
                segs.append(" ".join(cur))
                cur = []
            else:
                cur.append(tok)
        segs.append(" ".join(cur))
        cur = []
    steps = []
    for s in segs:
        slots = extract(s)
        if any(slots[k] for k in CRITICAL):
            steps.append((s.strip(), slots))
    return steps


def split_chain(text):
    """Slots only, in the order spoken."""
    return [slots for _, slots in split_chain_segments(text)]
