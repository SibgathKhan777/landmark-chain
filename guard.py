"""A deterministic check of an AI translation against what was said. No model, no learning: fixed tables.

The AI fallback (llm_fallback.py) can write fluent text that says something different from the source. In a real test of Evon on Kaggle it wrote
"the one on the LEFT at the second gate" for "right side" and dropped "two" from "after two lanes", and both read perfectly. This module pulls
the details that change a route out of BOTH the Hindi/Hinglish source and the AI's output, and rejects the output when they disagree:

    side (left/right), negation, question, condition (if/when/until), colours, numbers (spoken digits and counts)
    and, for three verbs only, WHO does it: standing, coming, and "where" ("where are you" is not "where am I")

It cannot check who does what for any other verb, or whether the whole sentence is faithful. A live test showed why the three verbs matter: Evon turned "where are you, I am standing here" into "tell me where I am, you are standing here", and everything else about it checked out. A rejection is safe: the rules' own
result (a partial translation or a refusal) is used instead. A pass means "these details match", not "the translation is correct".

    check(source, output, dst, src="hi-IN")  ->  list of problems (empty means the details match)
    src is "hi-IN" (Hindi/Hinglish, the default) or "kn-IN"; dst is "kn-IN", "hi-IN" or "en"
"""
import re
import unicodedata

from directions import G_CONDITION, H_LEFT, H_NEG, H_QUESTION, H_RIGHT
from textutil import norm, tokens

# ------------------------------------------------------------------------------------------------ the source (Hindi / Hinglish, either script)
COLOURS = {   # canonical name -> words in the source, words in Kannada, words in English
    "blue": ("ब्लू नीला नीली नीले neela neeli blue", "ನೀಲಿ", "blue"),
    "red": ("लाल रेड laal lal red", "ಕೆಂಪು", "red"),
    "green": ("हरा हरी हरे ग्रीन hara hari green", "ಹಸಿರು", "green"),
    "yellow": ("पीला पीली पीले येलो peela peeli yellow", "ಹಳದಿ", "yellow"),
    "white": ("सफेद सफ़ेद व्हाइट safed white", "ಬಿಳಿ", "white"),
    "black": ("काला काली काले ब्लैक kala kaala black", "ಕಪ್ಪು", "black"),
    "pink": ("गुलाबी gulabi pink", "ಗುಲಾಬಿ", "pink"),
    "orange": ("नारंगी ऑरेंज orange", "ಕಿತ್ತಳೆ", "orange"),
    "brown": ("भूरा भूरी ब्राउन brown", "ಕಂದು", "brown"),
}
SRC_COLOUR = {w: c for c, (ws, _, _) in COLOURS.items() for w in map(norm, ws.split())}

NUMBER_WORDS = {   # 1 is left out on purpose: "ek" / "एक" is mostly the article ("a gate"), so counting it would reject good translations
    2: "दो do two", 3: "तीन teen three", 4: "चार char four", 5: "पांच पाँच paanch panch five फाइव", 6: "छह छः chhe chhah six सिक्स",
    7: "सात saat seven सेवन", 8: "आठ aath eight एट", 9: "नौ nau nine नाइन", 10: "दस das ten टेन", 20: "बीस bees twenty", 50: "पचास pachas fifty",
    100: "सौ sau hundred",
}
SRC_NUMBER = {w: n for n, ws in NUMBER_WORDS.items() for w in map(norm, ws.split())}

KN_NUMBER = {2: "ಎರಡು", 3: "ಮೂರು", 4: "ನಾಲ್ಕು", 5: "ಐದು", 6: "ಆರು", 7: "ಏಳು", 8: "ಎಂಟು", 9: "ಒಂಬತ್ತು", 10: "ಹತ್ತು", 20: "ಇಪ್ಪತ್ತು", 50: "ಐವತ್ತು", 100: "ನೂರು"}
KN_STEMS = {n: w[:-1] if w.endswith("ು") else w for n, w in KN_NUMBER.items()}
KN_CARDINAL = {n: {w, st + "ಕ್ಕೆ", st + "ರ", st + "ರಲ್ಲಿ"} for n, w, st in ((n, KN_NUMBER[n], KN_STEMS[n]) for n in KN_NUMBER)}
KN_ORDINAL = {n: {st + "ನೇ", st + "ನೆಯ"} for n, st in KN_STEMS.items()}
# exact forms (two, second, for two, of two, in two), never a prefix: "ಹತ್ತಿರ" (near) starts like "ಹತ್ತು" (ten) and must not count as a number
EN_NUMBER = {2: "two second", 3: "three third", 4: "four fourth", 5: "five fifth", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 20: "twenty",
             50: "fifty", 100: "hundred"}
EN_NUM_WORD = {w: n for n, ws in EN_NUMBER.items() for w in ws.split()}
KN_DIGITS = {ord(c): str(i) for i, c in enumerate("೦೧೨೩೪೫೬೭೮೯")}

KN_NEG_WORDS = {"ಇಲ್ಲ", "ಅಲ್ಲ", "ಬೇಡ", "ಬೇಡಿ", "ಇಲ್ಲದೆ"}
KN_NEG_ENDINGS = ("ಬೇಡ", "ಬೇಡಿ", "ಿಲ್ಲ", "ಬಾರದು", "ಬಾರದ")        # "ಿಲ್ಲ" covers -ಲಿಲ್ಲ, -ತಿಲ್ಲ, -ದಿಲ್ಲ ("did not", "is not"); "ಇಲ್ಲಿ" (here) does not end this way
KN_COND_ENDINGS = ("ದಾಗ", "ದರೆ", "ವರೆಗೆ", "ವರೆಗೂ", "ತನಕ", "ಒಮ್ಮೆ")
KN_WH = ("ಎಲ್ಲಿ", "ಏನು", "ಯಾರು", "ಯಾವಾಗ", "ಹೇಗೆ", "ಯಾಕೆ", "ಏಕೆ", "ಎಷ್ಟು", "ಯಾವ")      # question words: a Kannada question need not carry a "?"
EN_WH = re.compile(r"\b(where|what|who|why|how|which)\b", re.I)
EN_NEG = re.compile(r"\b(not|no|never|don't|dont|doesn't|isn't|aren't|can't|cannot|won't|without)\b|n't\b", re.I)
EN_COND = re.compile(r"\b(if|when|whenever|until|unless|once|till)\b", re.I)


def _digits(text):
    """ASCII digits, with Kannada and Devanagari digits converted."""
    return "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)


def _joined(values):
    """Runs of two or more single digits ('six seven nine') are one number ('679'); anything else stays as it is."""
    out, run = set(), []
    for v in values + [None]:
        if isinstance(v, int) and v < 10:
            run.append(v)
            continue
        if len(run) >= 2:
            out.add("".join(map(str, run)))
        else:
            out.update(map(str, run))
        run = []
        if v is not None:
            out.add(str(v))
    return out


# ------------------------------------------------------------------------------------------------ who does it (standing, coming, "where")
COPULA = {norm("हूं"): {1}, norm("हूँ"): {1}, "hoon": {1}, "hun": {1}, "hu": {1}, norm("हो"): {2}, "ho": {2},
          norm("है"): {3}, "hai": {3}, norm("हैं"): {2, 3}, "hain": {2, 3}}                       # "हैं" is polite "you are" or "they are"
STAND_SRC = {norm(w) for w in "खड़ा खड़ी खड़े khada khadi khade".split()}
COME_SRC, PROGRESS_SRC = {"आ", "aa"}, {norm(w) for w in "रहा रही रहे raha rahi rahe rha rhi rhe".split()}
WHERE_SRC = {norm(w) for w in "कहाँ कहां kahan kahaan".split()}
KN_VERB = {"stand": ("ನಿಂತ",), "come": ("ಬರುತ್ತ", "ಬರ್ತ", "ಬರುತ್ತಿ"), "where": ("ಎಲ್ಲಿ",)}
KN_PERSON = ((1, ("ದ್ದೇನೆ", "ತ್ತೇನೆ", "ದ್ದೀನಿ", "ತ್ತೀನಿ", "ದ್ದೇವೆ", "ತ್ತೇವೆ")), (2, ("ದ್ದೀರಿ", "ತ್ತೀರಿ", "ದ್ದೀಯ", "ದ್ದೀಯಾ", "ತ್ತೀಯ", "ತ್ತೀಯಾ")),
             (3, ("ದ್ದಾನೆ", "ದ್ದಾಳೆ", "ತ್ತಾನೆ", "ತ್ತಾಳೆ", "ತ್ತಿದೆ")), (23, ("ದ್ದಾರೆ", "ತ್ತಾರೆ")))   # 23 = polite you / they
EN_PRONOUN = {"i": 1, "i'm": 1, "you": 2, "you're": 2, "he": 3, "he's": 3, "she": 3, "she's": 3}


def _kn_persons(word):
    for person, ends in KN_PERSON:
        if word.endswith(ends):
            return {23: {2, 3}}.get(person, {person})
    return None


def who_source(toks):
    """{verb: set of person-sets} said in the source: 'खड़ा हूँ' = (stand, I), 'कहाँ हो' = (where, you), 'आ रहा है' = (come, he)."""
    out = {}
    for i, t in enumerate(toks):
        verb = "stand" if t in STAND_SRC else "where" if t in WHERE_SRC else None
        nxt = [j for j in range(i + 1, min(len(toks), i + 3)) if toks[j] in COPULA]
        if verb and nxt:
            out.setdefault(verb, []).append(COPULA[toks[nxt[0]]])
        if t in COME_SRC and i + 2 < len(toks) and toks[i + 1] in PROGRESS_SRC and toks[i + 2] in COPULA:
            out.setdefault("come", []).append(COPULA[toks[i + 2]])
    return out


def who_output(text, dst):
    out = {}
    if dst == "kn-IN":
        words = text.replace("?", " ").replace(",", " ").replace(".", " ").replace(";", " ").split()
        for i, w in enumerate(words):
            for verb, stems in KN_VERB.items():
                if w.startswith(stems):
                    p = _kn_persons(w) or (_kn_persons(words[i + 1]) if verb == "where" and i + 1 < len(words) else None)
                    if p:
                        out.setdefault(verb, []).append(p)
    else:
        low = text.lower().replace("’", "'")
        for m in re.finditer(r"\bwhere\s+(?:(?:am|are|is)\s+(i|you|he|she)\b|(i|you|he|she)\s+(?:am|are|is)\b)", low):
            out.setdefault("where", []).append({EN_PRONOUN[m.group(1) or m.group(2)]})
        for m in re.finditer(r"\b(i|you|he|she)(?:\s+(?:am|are|is)|'m|'re|'s)\s+(standing|coming)\b", low):
            out.setdefault("stand" if m.group(2) == "standing" else "come", []).append({EN_PRONOUN[m.group(1)]})
    return out


def _num(digits):
    """'6' stays the single digit 6 (it can join a run: 6 7 9 = 679); a longer digit string stays as it is ('679', '100')."""
    return int(digits) if len(digits) == 1 else digits


# "दो" / "do" is "two" but also "give" ("दे दो", "bhej do"). It counts as the number two only before something that can be counted.
AMBIGUOUS_TWO = {norm("दो"), "do"}
COUNTED = {norm(w) for w in ("गली गलियां गलियों gali galiyan galiyon मिनट minute minutes min घंटे घंटा ghante ghanta मीटर meter metre किलोमीटर km कदम kadam बार baar "
                             "सिग्नल signal मोड़ mod गेट gate मकान ghar घर मंजिल फ्लोर floor बजे baje नंबर number दरवाजे door बिल्डिंग building चौराहे लेन lane "
                             "रास्ते rasta किलो kilo दिन din रुपये rupees लोग log ऑर्डर order पैकेट packet").split()}


def source_facts(text):
    toks = tokens(text)
    seq = []
    for i, t in enumerate(toks):
        d = _digits(t)
        if t in AMBIGUOUS_TWO and not (i + 1 < len(toks) and toks[i + 1] in COUNTED):
            seq.append(None)                                      # "give", not two
        else:
            seq.append(SRC_NUMBER[t] if t in SRC_NUMBER else _num(d) if d.isdigit() else None)
    return {
        "sides": ({"right"} if any(t in H_RIGHT for t in toks) else set()) | ({"left"} if any(t in H_LEFT for t in toks) else set()),
        "negation": any(t in H_NEG for t in toks),
        "question": "?" in text or any(t in H_QUESTION for t in toks),
        "condition": any(t in G_CONDITION for t in toks),
        "colours": {SRC_COLOUR[t] for t in toks if t in SRC_COLOUR},
        "numbers": _joined([v for v in seq if v is not None]),
    }


# ------------------------------------------------------------------------------------------------ the output
def output_facts(text, dst, ordinals=True):
    kn = dst == "kn-IN"
    if kn:
        words = text.replace("?", " ").replace(",", " ").replace(".", " ").replace(";", " ").split()
        seq = []
        for w in words:
            w2 = _digits(w.translate(KN_DIGITS))
            hit = next((n for n, forms in KN_CARDINAL.items() if w in forms), None)
            if hit is None and ordinals:                       # "second": counted in an output, but NOT required from a source (Hindi "dusra" can mean "another")
                hit = next((n for n, forms in KN_ORDINAL.items() if w in forms), None)
            seq.append(_num(w2) if w2.isdigit() else hit)
        sides = ({"right"} if "ಬಲ" in text else set()) | ({"left"} if "ಎಡ" in text else set())
        negation = any(w in KN_NEG_WORDS or w.endswith(KN_NEG_ENDINGS) for w in words)
        condition = any(w.endswith(KN_COND_ENDINGS) for w in words)
        colours = {c for c, (_, k, _) in COLOURS.items() if k in text}
    else:
        words = re.findall(r"[A-Za-z']+|\d+", text)
        seq = [_num(w) if w.isdigit() else EN_NUM_WORD.get(w.lower()) for w in words]
        idiom = re.compile(r"\b(all right|right (?:here|there|now|away)|right\?)", re.I)
        sides = {w.lower() for w in re.findall(r"[A-Za-z']+", idiom.sub(" ", text)) if w.lower() in ("left", "right")}
        negation = bool(EN_NEG.search(text))
        condition = bool(EN_COND.search(text))
        colours = {c for c, (_, _, e) in COLOURS.items() if re.search(rf"\b{e}\b", text, re.I)}
    wh = any(w.startswith(KN_WH) for w in words) if kn else bool(EN_WH.search(text))
    return {"sides": sides, "negation": negation, "question": "?" in text, "question_like": "?" in text or wh,
            "condition": condition, "colours": colours,
            "numbers": _joined([v for v in seq if v is not None])}


KN_Q_ENDINGS = ("ಬೇಕೇ", "ಬೇಕಾ", "ಬಹುದೇ", "ಬಹುದಾ", "ಅಲ್ಲವೇ", "ಅಲ್ವಾ", "ಅಲ್ಲವಾ")      # Kannada yes/no questions end in a particle, with no "?" from Prisma


def facts(text, lang, source=False):
    """The checked details of a text in Hindi/Hinglish ('hi-IN'), Kannada ('kn-IN') or English ('en')."""
    if lang == "hi-IN":
        f = source_facts(text)
        f["question_like"] = f["question"]
        f["who"] = who_source(tokens(text))
        return f
    kind = "kn-IN" if lang == "kn-IN" else "en"
    f = output_facts(text, kind, ordinals=not source)
    f["who"] = who_output(text, kind)
    if source and kind == "kn-IN":                       # a spoken Kannada question may carry neither "?" nor a question word
        f["question"] = f["question_like"] or any(w.endswith(KN_Q_ENDINGS) for w in text.replace("?", " ").split())
    elif source:
        f["question"] = f["question_like"]
    return f


def check(source, output, dst, src="hi-IN"):
    """Problems found between the source (Hindi/Hinglish by default, or Kannada with src='kn-IN') and the AI output; empty means the details agree."""
    problems = []
    out = output.strip()
    if not out:
        return ["empty output"]
    if "[unclear]" in out.lower():
        problems.append("the model marked part of it as unclear")
    letters = [c for c in out if c.isalpha()]
    if dst == "kn-IN" and letters and sum("ಀ" <= c <= "೿" for c in letters) < 0.6 * len(letters):
        problems.append("not mostly Kannada script")
    if dst == "en" and letters and sum(c.isascii() for c in letters) < 0.9 * len(letters):
        problems.append("not English")
    if dst == "hi-IN" and letters and sum("\u0900" <= c <= "\u097f" for c in letters) < 0.6 * len(letters):
        problems.append("not mostly Devanagari script")
    if out.lower() == source.strip().lower():
        problems.append("the output is the source copied back")
    s, o = facts(source, src, source=True), facts(out, dst)
    if s["sides"] != o["sides"]:
        problems.append(f"side: said {sorted(s['sides']) or 'none'}, output {sorted(o['sides']) or 'none'}")
    if s["negation"] != o["negation"]:
        problems.append(f"negation: source {'has' if s['negation'] else 'has no'} negation, output {'has' if o['negation'] else 'has none'}")
    if s["question"] and not o["question_like"]:                          # a question must still read as one (a "?" or a question word) ...
        problems.append("question: source is a question, output is not")
    elif o["question"] and not s["question"]:                              # ... and a statement must not turn into one
        problems.append("question: source is not a question, output is")
    if s["condition"] != o["condition"]:
        problems.append(f"condition: source {'has' if s['condition'] else 'has no'} if/when/until, output {'has' if o['condition'] else 'has none'}")
    if s["colours"] != o["colours"]:
        problems.append(f"colour: said {sorted(s['colours']) or 'none'}, output {sorted(o['colours']) or 'none'}")
    ws, wo = s["who"], o["who"]
    for verb in ws.keys() & wo.keys():                                    # only where both sides name the same verb: otherwise there is nothing to compare
        said = {p for ps in ws[verb] for p in ps}
        gave = {p for ps in wo[verb] for p in ps}
        if said.isdisjoint(gave):
            who = {1: "I/we", 2: "you", 3: "he/she/they"}
            problems.append(f"who: '{verb}' is said of {'/'.join(who[p] for p in sorted(said))}, output says it of {'/'.join(who[p] for p in sorted(gave))}")
    missing = s["numbers"] - o["numbers"]
    if missing:
        problems.append(f"number: {sorted(missing)} said but not in the output")
    return problems
