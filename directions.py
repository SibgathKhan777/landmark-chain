"""Directions and plans for the call interpreter: a small CLOSED grammar, rule-based, no LLM, no machine translation.

A delivery call is mostly instructions ("come straight, take a right, you will see a building ahead, wait there, I am coming").
Each instruction is one *clause* with a fixed shape, found by matching trigger words. A clause is a dict:

    {"act": STRAIGHT | TURN | SEE_AHEAD | WAIT | COMING | SEEN | STANDING, ...slots}

Seven shapes only. Anything else in the sentence (times, reasons, small talk) is reported as not understood.
What each language can UNDERSTAND (parse) and WRITE (render):

    parse:   Hindi (Devanagari and Roman) -> all seven      Kannada -> COMING, SEEN, STANDING (a rider's replies)
             English -> STRAIGHT, TURN, SEE_AHEAD, WAIT (a customer's directions; the call where the customer speaks English)
    render:  Hindi, Kannada and English -> all seven

Safety rules: a sentence with a negation ("do not turn right") or a question ("should I go straight?") is refused, because a
statement written from it would say the opposite, or something that was not said. Two opposite turns ("right, left") are refused.
The Kannada wording was drafted without a native-speaker review (see kannada_review.md).
"""
from extraction import extract, matched_tokens
from textutil import norm, tokens


def _set(*words):
    return {norm(w) for w in words}


# ------------------------------------------------------------------------------------------------ Hindi trigger words
H_STRAIGHT = _set("सीधे", "सीधा", "सीधी", "seedhe", "seedha", "sidhe", "sidha", "seedhi", "straight", "स्ट्रेट")
H_COME = _set("आ", "आओ", "आइए", "आइये", "आना", "आएं", "aa", "aao", "aaiye", "aana", "aayiye")
H_GO = _set("चलो", "चलिए", "चलिये", "जाओ", "जाइए", "जाइये", "जाना", "चलना", "जाएं", "chalo", "chaliye", "jao", "jaiye", "jana", "go", "गो")
H_RIGHT = _set("राइट", "right", "दाएं", "दायें", "दायीं", "दाईं", "दाहिने", "दाहिनी", "दाहिना", "daayi", "daai", "dayi", "dahine", "daye", "dayen")
H_LEFT = _set("लेफ्ट", "left", "बाएं", "बायें", "बायीं", "बाईं", "बाया", "baayi", "baai", "bayi", "baye", "bayen")
H_TURN = _set("ले", "लो", "लेना", "लीजिए", "लीजिये", "लें", "मुड़", "मुड़ो", "मुड़ना", "मुड़िए", "मुड़िये", "मुड़ें", "घूम", "घूमो",
              "घूमिए", "मोड़", "हो", "होजाओ", "hojao", "ho", "mudo", "mud", "mudna", "mudja", "mudjao", "mudiye", "le", "lo", "leke", "ghumo",
              "टर्न", "turn", "कर", "करो", "करना", "kar", "karo", "karna", "take", "टेक")
H_SEE_AHEAD = _set("दिखेगी", "दिखेगा", "दिखेंगे", "दिखेगे", "दिखाई", "देखेगा", "देखोगे", "देखेंगे", "dikhegi", "dikhega", "dekhega", "dikhai", "dekhoge")
H_SEEN = _set("दिख", "दिखी", "दिखा", "दिखाई")           # "दिख गई" / "दिखाई दी"
H_DONE = _set("गई", "गयी", "गया", "गए", "दी", "दिया", "gayi", "gaya")
H_FRONT = _set("सामने", "samne", "saamne")
H_WAIT = _set("ठहरो", "ठहरिए", "ठहरिये", "ठहरना", "रुको", "रुकिए", "रुकिये", "रुकना", "ठहर", "रुक", "wait", "ruko", "rukiye", "thehro", "theharo",
              "tehro", "thehriye", "tehriye", "thehro", "वेट", "ruk", "rukna")
H_THERE = _set("वहाँ", "वहां", "वहीं", "wahan", "wahaan", "waha", "vahan", "vahaan", "wahin", "vahin")
H_HERE = _set("यहाँ", "यहां", "यहीं", "yahan", "yahaan", "yaha", "yahin")
H_STAND = _set("खड़ा", "खड़ी", "खड़े", "खड़ा हूँ", "khada", "khadi")
H_I_AM = _set("हूँ", "हूं", "hoon", "hun", "hu")
H_PROGRESS = _set("रहा", "रही", "रहे", "raha", "rahi", "rahe", "rha", "rhi", "rhe")
H_NEG = _set("नहीं", "नही", "मत", "nahi", "nahin", "mat", "ग़लत", "गलत")
H_QUESTION = _set("क्या", "कब", "कहाँ", "कहां", "कैसे", "कौन", "kya", "kab", "kahan", "kaise", "kaun",
                  "जाऊं", "जाऊँ", "आऊं", "आऊँ", "चलूं", "चलूँ", "aaun", "aaoon", "jaun", "jaaun", "या", "ya")   # "should I come?" has no question word
H_HAATH = _set("हाथ", "haath", "hath", "haat")                     # "सीधे हाथ" is the right hand, not "straight"
H_RIGHT_HAND, H_LEFT_HAND = _set("सीधे", "सीधा", "seedhe", "seedha", "sidhe", "sidha"), _set("उल्टे", "उल्टा", "ulte", "ulta")
H_TURN_FILL = _set("साइड", "side", "हाथ", "hand", "haath", "hath", "पर", "pe", "par", "की", "ki", "का", "ka", "तरफ", "taraf", "से", "a", "ए", "the")
H_AFTER_WAIT = _set("कर", "करो", "करना", "कीजिए", "कीजिये", "kar", "karo", "kijiye", "kijiyega", "जाओ", "जाना", "jao", "jana")
H_JAYEGA = _set("जाएगी", "जाएगा", "जायेगी", "जायेगा", "जाएंगी", "jayegi", "jayega", "jaayegi", "jaayega", "jaegi", "jaega")
H_DIKH = _set("दिख", "dikh")
H_FIRST = _set("पहले", "pehle", "pahle")
SEQUENCERS = _set("फिर", "phir", "fir", "then", "बाद", "baad", "उसके", "uske")

# Words that, left over next to a recognised instruction, would change what it means. A partial translation would then say
# something different from what was meant, so the whole sentence is refused instead (reason in brackets).
G_CONDITION = _set("अगर", "जब", "तब", "यदि", "तक", "agar", "jab", "tab", "yadi", "tak", "दिखे", "दिखें", "दिखने", "दिखता", "dikhe", "dikhne",
                   "मिले", "मिलने", "mile", "milne")                                         # (condition) "when you see the building, turn"
G_THIRD = _set("वो", "वह", "वे", "उसका", "उसकी", "उसके", "उनका", "उसे", "wo", "woh", "vo", "usko", "driver", "ड्राइवर", "दोस्त", "dost",
               "था", "थी", "tha", "thi", "रहा", "रही", "रहे", "raha", "rahi", "rahe", "rha", "rhi", "rhe")   # (third person) a statement about someone else
G_DISTANCE = _set("मीटर", "meter", "metre", "किलोमीटर", "km", "kilometer", "कदम", "kadam", "फीट", "feet", "गली", "gali", "सिग्नल", "signal",
                  "मोड़", "mod", "चौराहा", "चौराहे", "chauraha")                              # (distance) "after two lanes", "100 metres"
G_TURN_NO_SIDE = _set("टर्न", "turn", "मुड़", "मुड़ो", "मुड़ना", "मुड़िए", "मुड़िये", "मुड़ें", "mud", "mudo", "mudna", "mudja", "mudjao", "घूम", "घूमो",
                      "घूमिए", "ghumo")                                                      # a turn with no side said, such as "u turn"

# ------------------------------------------------------------------------------------------------ Kannada trigger words
K_COMING = _set("ಬರುತ್ತಿದ್ದೇನೆ", "ಬರುತ್ತಿದ್ದೀನಿ", "ಬರ್ತಿದ್ದೀನಿ", "ಬರ್ತಿದ್ದೇನೆ")
K_SEEN = _set("ಕಾಣಿಸಿತು", "ಕಾಣಿಸಿದೆ", "ಕಂಡಿತು", "ಕಂಡಿದೆ", "ಕಾಣುತ್ತಿದೆ", "ಕಾಣಿಸುತ್ತಿದೆ", "ಕಾಣಿಸ್ತಿದೆ", "ಕಾಣ್ತಿದೆ")
K_STAND = _set("ನಿಂತಿದ್ದೇನೆ", "ನಿಂತಿದ್ದೀನಿ", "ನಿಂತಿರುವೆ", "ನಿಂತಿರುತ್ತೇನೆ", "ನಿಂತಿದ್ದೀನಿ")
K_NEG = _set("ಬೇಡ", "ಅಲ್ಲ", "ಇಲ್ಲ", "ಇಲ್ಲಾ", "ಸಿಗಲಿಲ್ಲ", "ಕಾಣುತ್ತಿಲ್ಲ", "ಕಾಣಿಸುತ್ತಿಲ್ಲ", "ಕಾಣಲಿಲ್ಲ")
K_QUESTION = _set("ಏನು", "ಎಲ್ಲಿ", "ಯಾವಾಗ", "ಹೇಗೆ", "ಯಾವ", "ಯಾರು", "ಏಕೆ", "ಎಷ್ಟು")

# ------------------------------------------------------------------------------------------------ writing the clauses
# English (the customer speaks English). A closed grammar of its own, because English word order is not the Hindi one.
E_STRAIGHT = _set("straight")
E_GO = _set("go", "going", "keep", "continue", "ride", "drive", "walk", "proceed")
E_COME = _set("come", "coming")
E_TURN = _set("turn", "take", "make")
E_RIGHT, E_LEFT = _set("right"), _set("left")
E_TURN_FILL = _set("a", "an", "the", "hand", "side", "on", "your", "to", "at", "and", "then")
E_WAIT = _set("wait", "stay", "stop")
E_THERE, E_HERE = _set("there"), _set("here")
E_SEE, E_WILL = _set("see", "spot"), _set("will", "ll")
E_ART = _set("a", "an", "the", "ahead", "in", "front", "of", "you", "straight")
E_NEG = _set("not", "no", "never", "dont", "don", "t", "cannot", "cant", "wont", "without", "stop")
E_QUESTION = _set("what", "where", "when", "how", "which", "who", "why", "should", "shall", "can", "could", "would", "do", "does", "did", "is", "are", "may")
E_CONDITION = _set("if", "when", "whenever", "once", "until", "unless", "while", "before", "after", "as", "since", "because")
E_THIRD = _set("he", "she", "they", "him", "his", "her", "them", "their", "driver", "friend", "rider", "guy", "boy", "man", "someone", "somebody", "brother", "sister")
E_DISTANCE = _set("meter", "meters", "metre", "metres", "km", "kilometer", "kilometers", "kilometre", "kilometres", "feet", "foot", "block", "blocks", "signal", "signals",
                  "street", "streets", "lane", "lanes", "mile", "miles", "step", "steps")
E_TURN_NO_SIDE = _set("turn", "uturn", "u")
# "right" that is not a direction: "that is right", "right here", "all right". Removed before parsing, so it is never read as a turn.
E_RIGHT_IDIOMS = ["that is right", "that s right", "it is right", "it s right", "you are right", "you re right", "all right", "alright", "right now",
                  "right here", "right there", "right away", "right behind", "right in front"]


def clean_english(text):
    """English speech with the non-direction "right" taken out ("Yes, that is right"). Returns normalised text."""
    t = " " + norm(text) + " "
    for idiom in E_RIGHT_IDIOMS:
        t = t.replace(f" {idiom} ", " " + " ".join(w for w in idiom.split() if w != "right") + " ")
    return " ".join(t.split())


HI_NP_GENDER = {"GATE": "m", "HOUSE": "m", "SHOP": "f", "LANE": "f", "FLAT": "m", "DOOR": "m", "BUILDING": "f", "FLOOR": "f"}


def _np(slots, lang):
    """Noun phrase for what is seen ("blue gate"), written by the landmark tables. None when they cannot write it."""
    import translate                      # late import: translate imports this module
    return translate.render(slots, lang)


def render(clause, lang):
    """One clause written in `lang` ('hi-IN', 'kn-IN' or 'en'); None when the tables cannot write it."""
    a = clause["act"]
    if a == "STRAIGHT":
        verb = clause["verb"]
        return {"hi-IN": {"come": "सीधे आइए", "go": "सीधे जाइए"}, "kn-IN": {"come": "ನೇರವಾಗಿ ಬನ್ನಿ", "go": "ನೇರವಾಗಿ ಹೋಗಿ"},
                "en": {"come": "come straight", "go": "go straight"}}[lang][verb]
    if a == "TURN":
        return {"hi-IN": {"RIGHT": "दाएं मुड़िए", "LEFT": "बाएं मुड़िए"}, "kn-IN": {"RIGHT": "ಬಲಕ್ಕೆ ತಿರುಗಿ", "LEFT": "ಎಡಕ್ಕೆ ತಿರುಗಿ"},
                "en": {"RIGHT": "turn right", "LEFT": "turn left"}}[lang][clause["side"]]
    if a == "WAIT":
        place = clause.get("place")
        return {"hi-IN": {"THERE": "वहाँ रुकिए", "HERE": "यहाँ रुकिए", None: "रुकिए"},
                "kn-IN": {"THERE": "ಅಲ್ಲಿ ನಿಲ್ಲಿ", "HERE": "ಇಲ್ಲಿ ನಿಲ್ಲಿ", None: "ನಿಲ್ಲಿ"},
                "en": {"THERE": "wait there", "HERE": "wait here", None: "wait"}}[lang][place]
    if a == "COMING":            # Hindi uses the polite plural "वे", because the interpreter does not know the speaker's gender
        return {"hi-IN": "वे आ रहे हैं", "kn-IN": "ನಾನು ಬರುತ್ತಿದ್ದೇನೆ", "en": "I am coming"}[lang]
    if a == "STANDING":          # "here" is written only when it was said
        here = clause.get("place") == "HERE"
        return {"hi-IN": "वे यहाँ खड़े हैं" if here else "वे खड़े हैं", "kn-IN": "ನಾನು ಇಲ್ಲಿ ನಿಂತಿದ್ದೇನೆ" if here else "ನಾನು ನಿಂತಿದ್ದೇನೆ",
                "en": "I am standing here" if here else "I am standing"}[lang]
    if a in ("SEE_AHEAD", "SEEN"):
        np = _np(clause["slots"], lang)
        if np is None:
            return None
        if a == "SEE_AHEAD":
            if lang == "hi-IN":
                (t,) = clause["slots"]["target"] or ["BUILDING"]
                return f"सामने {np} {'दिखेगी' if HI_NP_GENDER.get(t) == 'f' else 'दिखेगा'}"
            return {"kn-IN": f"ಎದುರು {np} ಕಾಣಿಸುತ್ತದೆ", "en": f"you will see a {np} ahead"}[lang]
        if lang == "hi-IN":
            (t,) = clause["slots"]["target"] or ["BUILDING"]
            return f"{np} {'दिख गई' if HI_NP_GENDER.get(t) == 'f' else 'दिख गया'}"
        return {"kn-IN": f"{np} ಕಾಣಿಸಿತು", "en": f"I can see the {np}"}[lang]
    return None


# ------------------------------------------------------------------------------------------------ understanding the clauses
def _np_slots(toks):
    """Landmark words inside a 'what is seen' phrase: colour, ordinal and one thing to point at. None if it has anything else."""
    s = extract(" ".join(toks))
    if s["anchor"] or s["relation"] or s["side"] or len(s["target"]) != 1 or len(s["colour"]) > 1 or len(s["ordinal"]) > 1:
        return None
    return {k: set(v) for k, v in s.items()}


def _parse_hi(toks):
    clauses, used = [], set()
    n = len(toks)

    def take(i, cl, *idx):
        cl["span"] = (min(idx), max(idx))
        clauses.append((min(idx), cl)); used.update(idx)

    def side_at(i):
        """('RIGHT'|'LEFT', token indexes) when token i names a side, including the idiom "सीधे हाथ" (right hand) and "उल्टे हाथ" (left hand)."""
        t = toks[i]
        if t in H_RIGHT:
            return "RIGHT", [i]
        if t in H_LEFT:
            return "LEFT", [i]
        if i + 1 < n and toks[i + 1] in H_HAATH:
            if t in H_RIGHT_HAND:
                return "RIGHT", [i, i + 1]
            if t in H_LEFT_HAND:
                return "LEFT", [i, i + 1]
        return None, []

    for i, t in enumerate(toks):
        if i in used:
            continue
        window = lambda lo, hi: [j for j in range(max(0, lo), min(n, hi)) if j not in used]
        side, side_idx = side_at(i)
        if side:                                                      # "राइट ले लो" / "दाएं मुड़ो" / "right hojao" / "सीधे हाथ पर मुड़ो"
            verbs = [j for j in window(i - 3, i + 5) if toks[j] in H_TURN and j not in side_idx]
            if verbs:
                lo, hi = min(side_idx[0], verbs[0]), max(side_idx[-1], verbs[0])
                fill = [j for j in window(lo, hi + 1) if toks[j] in H_TURN_FILL and j not in side_idx]
                extra, j = [], max(side_idx[-1], verbs[0]) + 1     # only the verbs right after it ("turn kar lo"), never the next clause's
                while j < n and j not in used and toks[j] in H_TURN | H_GO:
                    extra.append(j); j += 1
                take(i, {"act": "TURN", "side": side}, *side_idx, verbs[0], *fill, *extra)
        elif t in H_STRAIGHT:                                         # "सीधे आ जाओ" / "सीधे चलो"
            come = [j for j in window(i - 2, i + 4) if toks[j] in H_COME]
            go = [j for j in window(i - 2, i + 4) if toks[j] in H_GO]
            if come:
                extra = [j for j in window(come[0], come[0] + 3) if toks[j] in H_GO]      # the "जाओ" of "आ जाओ"
                take(i, {"act": "STRAIGHT", "verb": "come"}, i, come[0], *extra)
            elif go:
                take(i, {"act": "STRAIGHT", "verb": "go"}, i, go[0])
        elif t in H_FRONT:                                            # "सामने बिल्डिंग दिखेगी"
            see = [(j, ()) for j in window(i + 1, i + 6) if toks[j] in H_SEE_AHEAD]
            see += [(j, (j + 1,)) for j in window(i + 1, i + 6) if toks[j] in H_DIKH and j + 1 < n and toks[j + 1] in H_JAYEGA]    # "दिख जाएगी"
            see.sort()
            if see:
                at, more = see[0]
                between = [j for j in range(i + 1, at) if j not in used]
                slots = _np_slots([toks[j] for j in between])
                if slots is not None:
                    extra = [j for j in window(at + 1, at + 2) if toks[j] in _set("देगी", "देगा", "देंगे", "दे")]
                    take(i, {"act": "SEE_AHEAD", "slots": slots}, i, *between, at, *more, *extra)
        elif t in H_WAIT:                                             # "वहाँ ठहरो"
            place = None
            near = [j for j in window(i - 2, i + 3) if toks[j] in H_THERE | H_HERE]
            idx = [i]
            if near:
                place = "THERE" if toks[near[0]] in H_THERE else "HERE"
                idx.append(near[0])
            idx += [j for j in window(i + 1, i + 4) if toks[j] in H_AFTER_WAIT]          # "वेट करो", "रुक जाओ"
            take(min(idx), {"act": "WAIT", "place": place}, *idx)
        elif t in H_PROGRESS:                                         # "मैं आ रहा हूँ"
            if i >= 1 and toks[i - 1] in H_COME and i + 1 < n and toks[i + 1] in H_I_AM:
                idx = [i - 1, i, i + 1] + ([i - 2] if i >= 2 and toks[i - 2] in _set("मैं", "main", "mai", "mein") else [])
                take(min(idx), {"act": "COMING"}, *idx)
    # "बिल्डिंग दिख गई" (seen) — needs a seen-word followed by a done-word
    for i, t in enumerate(toks):
        if t in H_SEEN and i not in used and i + 1 < n and toks[i + 1] in H_DONE and i + 1 not in used:
            before = [j for j in range(max(0, i - 3), i) if j not in used]
            slots = _np_slots([toks[j] for j in before]) if before else None
            if slots is not None:
                take(min(before), {"act": "SEEN", "slots": slots}, *before, i, i + 1)
    for i, t in enumerate(toks):                                      # "मैं यहाँ खड़ा हूँ"
        if t in H_STAND and i not in used and i + 1 < n and toks[i + 1] in H_I_AM:
            here = [j for j in range(max(0, i - 3), i) if toks[j] in H_HERE and j not in used]
            idx = [i, i + 1] + here + [j for j in range(max(0, i - 3), i) if toks[j] in _set("मैं", "main", "mai") and j not in used]
            take(min(idx), {"act": "STANDING", "place": "HERE" if here else None}, *idx)
    for start, _ in clauses:                                          # "पहले लेफ्ट लो फिर राइट लो": "पहले" here means "first", not the ordinal "first gate"
        if start >= 1 and toks[start - 1] in H_FIRST and start - 1 not in used:
            used.add(start - 1)
    return clauses, used


def _parse_en(toks):
    clauses, used = [], set()
    n = len(toks)

    def take(cl, *idx):
        cl["span"] = (min(idx), max(idx))
        clauses.append((min(idx), cl)); used.update(idx)

    window = lambda lo, hi: [j for j in range(max(0, lo), min(n, hi)) if j not in used]
    for i, t in enumerate(toks):                                         # "take a right" / "turn left" / "make a left turn"
        if i in used or (t not in E_RIGHT and t not in E_LEFT):
            continue
        verbs = [j for j in window(i - 3, i + 4) if toks[j] in E_TURN]
        if verbs:
            lo, hi = min(i, verbs[0]), max(i, verbs[0])
            fill = [j for j in window(lo, hi + 1) if toks[j] in E_TURN_FILL]
            tail = [j for j in window(hi + 1, hi + 2) if toks[j] in E_TURN]                    # "take a right turn"
            take({"act": "TURN", "side": "RIGHT" if t in E_RIGHT else "LEFT"}, i, verbs[0], *fill, *tail)
    for i, t in enumerate(toks):
        if i in used:
            continue
        if t in E_STRAIGHT:                                              # "go straight" / "come straight" / "keep going straight"
            come = [j for j in window(i - 3, i + 3) if toks[j] in E_COME]
            go = [j for j in window(i - 3, i + 3) if toks[j] in E_GO]
            if come or go:
                take({"act": "STRAIGHT", "verb": "come" if come else "go"}, i, (come or go)[0])
        elif t in E_SEE and i >= 1:                                      # "you will see a building ahead" / "you'll see the blue gate"
            before = [j for j in window(i - 3, i) if toks[j] in E_WILL]
            if before:
                words, glue = [], []
                for j in range(i + 1, min(n, i + 7)):                    # "a blue gate ahead": stop at the first word that is neither glue nor a landmark word
                    if j in used:
                        break
                    if toks[j] in E_ART:
                        glue.append(j)
                    elif matched_tokens(toks[j]):
                        words.append(j)
                    else:
                        break
                slots = _np_slots([toks[j] for j in words]) if words else None
                if slots is not None:
                    you = [j for j in window(i - 4, i) if toks[j] in _set("you")]
                    take({"act": "SEE_AHEAD", "slots": slots}, i, before[0], *you, *words, *glue)
        elif t in E_WAIT:                                                # "wait there" / "wait here" / "please wait"
            near = [j for j in window(i - 2, i + 3) if toks[j] in E_THERE | E_HERE]
            place = None
            idx = [i]
            if near:
                place = "THERE" if toks[near[0]] in E_THERE else "HERE"
                idx.append(near[0])
            take({"act": "WAIT", "place": place}, *idx)
    return clauses, used


def _parse_kn(toks):
    clauses, used = [], set()
    for i, t in enumerate(toks):
        if t in K_COMING:
            clauses.append((i, {"act": "COMING"})); used.add(i)
            if i and toks[i - 1] in _set("ನಾನು"):
                used.add(i - 1)
        elif t in K_STAND:
            here = any(toks[j] == norm("ಇಲ್ಲಿ") for j in range(max(0, i - 3), i))
            clauses.append((i, {"act": "STANDING", "place": "HERE" if here else None})); used.add(i)
            for j in range(max(0, i - 3), i):
                if toks[j] in _set("ನಾನು", "ಇಲ್ಲಿ"):
                    used.add(j)
        elif t in K_SEEN:
            before = [j for j in range(max(0, i - 3), i) if j not in used]
            slots = _np_slots([toks[j] for j in before]) if before else None
            if slots is not None:
                clauses.append((min(before), {"act": "SEEN", "slots": slots})); used.update(before); used.add(i)
    return clauses, used


def parse(text, lang):
    """-> (clauses in spoken order, token indexes they used, tokens, refusal reason or None).

    A reason is given only when a clause was found, because the clause would otherwise be written without it:
      negation, question                      "do not turn right", "should I come straight?"
      conflict                                two opposite turns with nothing between them ("right left")
      condition, third_person, distance       left-over words that change what the instruction means
      unsupported_combination                 a turn with no side said ("u turn")"""
    toks = tokens(text)
    clauses, used = {"hi-IN": _parse_hi, "en": _parse_en}.get(lang, _parse_kn)(toks)
    clauses = [c for _, c in sorted(clauses, key=lambda p: p[0])]
    reason = None
    if clauses:
        neg, qs = {"hi-IN": (H_NEG, H_QUESTION), "en": (E_NEG, E_QUESTION)}.get(lang, (K_NEG, K_QUESTION))
        if lang == "en":       # "stop" is a waiting verb here, so "do not stop here" is caught by "not"; a bare "stop" is not a negation
            neg = neg - _set("stop")
        left = [t for i, t in enumerate(toks) if i not in used]
        turns = [c for c in clauses if c["act"] == "TURN"]
        if any(t in neg for t in toks):
            reason = "negation"
        elif "?" in text or any(t in qs for t in toks):
            reason = "question"
        elif any(a["side"] != b["side"] and not any(t in SEQUENCERS for t in toks[a["span"][1] + 1:b["span"][0]])
                 for a, b in zip(turns, turns[1:])):
            reason = "conflict"
        elif lang in ("hi-IN", "en") and any(t in (G_CONDITION if lang == "hi-IN" else E_CONDITION) for t in left):
            reason = "condition"
        elif lang in ("hi-IN", "en") and any(t in (G_THIRD if lang == "hi-IN" else E_THIRD) for t in left):
            reason = "third_person"
        elif lang in ("hi-IN", "en") and (any(t in (G_DISTANCE if lang == "hi-IN" else E_DISTANCE) for t in left) or any(t.isdigit() for t in left)):
            reason = "distance"
        elif lang in ("hi-IN", "en") and any(t in (H_RIGHT | H_LEFT if lang == "hi-IN" else E_RIGHT | E_LEFT) for t in left) and not extract(" ".join(left))["target"]:
            reason = "conflict" if turns else "unsupported_combination"      # a side that belongs to no landmark, e.g. "right left hojao"
        elif lang in ("hi-IN", "en") and any(t in (G_TURN_NO_SIDE if lang == "hi-IN" else E_TURN_NO_SIDE) for t in left):
            reason = "unsupported_combination"
    return clauses, used, toks, reason
