"""Hinglish edge cases for the call interpreter, with the CORRECT outcome written down per case. Text level: no API calls.

Each case is (group, text, expected) where expected is one of
    ("translated", [clauses])   all of it, as these clauses in this order
    ("partial", [clauses])      these clauses, and the leftover words are harmless (fillers, times) and are announced
    ("refused", reason)         refused; reason is the refusal code, or None when any refusal is right

The tests (tests/test_hinglish.py) enforce every case, so a change that makes the interpreter say something different, or less than
was meant, fails. The "real Prisma" cases are transcripts that the real Prisma returned for a Hinglish voice (out/hinglish_prisma.json).

    python experiments/hinglish_edge_cases.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from translate import translate  # noqa: E402

S, T, V, W, C = "STRAIGHT", "TURN", "SEE_AHEAD", "WAIT", "COMING"
tr, pa, no = "translated", "partial", "refused"
CASES = [
    ("the sentence itself", "bhaiya seedhe aa jao right le lo phir samne building dikhegi wahan ruko main aa raha hoon", (tr, [S, T, V, W, C])),
    ("the sentence itself", "भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ", (tr, [S, T, V, W, C])),
    # --- English words in Hindi sentences
    ("English words, Roman", "straight aa jao", (tr, [S])),
    ("English words, Roman", "seedha aao phir right turn kar lo", (tr, [S, T])),
    ("English words, Roman", "wait karo main aa raha hu", (tr, [W, C])),
    ("English words, Roman", "left side mud jao", (tr, [T])),
    ("English words, Roman", "right hand side pe mudna", (tr, [T])),
    ("English words, Roman", "go straight and take a right", (tr, [S, T])),
    ("English words, Devanagari", "स्ट्रेट आ जाओ", (tr, [S])),
    ("English words, Devanagari", "टर्न राइट कर लो", (tr, [T])),
    ("English words, Devanagari", "वेट करो", (tr, [W])),
    ("English words, Devanagari", "लेफ्ट साइड मुड़ जाओ", (tr, [T])),
    # --- spelling and speech variants
    ("variants", "सीधा आओ दाएं मुड़ो", (tr, [S, T])),
    ("variants", "ek dum seedha aao", (pa, [S])),
    ("variants", "दाहिने हाथ पर मुड़ जाइए", (tr, [T])),
    ("variants", "बाएं हाथ की तरफ मुड़ो", (tr, [T])),
    ("variants", "सीधे हाथ पर मुड़ो", (tr, [T])),            # "सीधे हाथ" is the RIGHT hand, not "straight"
    ("variants", "उल्टे हाथ पर मुड़ो", (tr, [T])),            # the LEFT hand
    ("variants", "seedhe haath pe mudo", (tr, [T])),
    ("variants", "yahin ruko", (tr, [W])),
    ("variants", "ruk jao wahan", (tr, [W])),
    ("variants", "main aa gaya", (no, None)),
    ("variants", "aa rha hu", (tr, [C])),
    ("variants", "मैं आ रही हूँ", (tr, [C])),
    ("variants", "बिल्डिंग के सामने ठहरो", (no, None)),
    ("variants", "samne building dikh jayegi", (tr, [V])),
    ("variants", "सामने नीला गेट दिखेगा", (tr, [V])),
    ("variants", "aap wahan wait kijiye main five minute mein aa raha hoon", (pa, [W, C])),
    # --- routes with more than one turn
    ("multi-step routes", "pehle left lo phir right lo", (tr, [T, T])),
    ("multi-step routes", "बाएं मुड़ो फिर दाएं मुड़ो", (tr, [T, T])),
    ("multi-step routes", "दाएं मुड़ो फिर बाएं मुड़ो", (tr, [T, T])),
    ("multi-step routes", "right le lo phir seedha aao", (tr, [T, S])),
    ("multi-step routes", "ruko main aa raha hoon phir seedha aana", (tr, [W, C, S])),
    ("multi-step routes", "राइट ले लो लेफ्ट ले लो", (no, "conflict")),          # two opposite turns, nothing between them
    ("multi-step routes", "right left hojao", (no, "conflict")),
    # --- distances, counts, turns with no side: a table cannot write them
    ("distances and counts", "dusra right le lo", (no, None)),
    ("distances and counts", "दूसरी गली से दाएं मुड़ो", (no, None)),
    ("distances and counts", "100 meter seedha aao", (no, "distance")),
    ("distances and counts", "दो गली बाद राइट ले लो", (no, "distance")),
    ("distances and counts", "dusre signal se left le lo", (no, None)),
    ("distances and counts", "seedhe jao phir u turn le lo", (no, "unsupported_combination")),
    ("distances and counts", "peeche aa jao", (no, None)),
    # --- negation
    ("negation", "right mat lena seedha aao", (no, "negation")),
    ("negation", "left nahi right lo", (no, "negation")),
    ("negation", "ruko mat seedha aao", (no, "negation")),
    ("negation", "सीधे मत आना", (no, "negation")),
    ("negation", "building nahi dikhegi", (no, None)),
    ("negation", "seedhe aa jao nahi to main late ho jaunga", (no, "negation")),
    # --- questions, with and without a question word
    ("questions", "kya main seedha aaun", (no, None)),
    ("questions", "building dikh rahi hai?", (no, None)),
    ("questions", "right lena hai ya left", (no, None)),
    ("questions", "सीधे आ जाऊं", (no, "question")),
    ("questions", "seedha jaun", (no, None)),
    # --- conditions: dropping the condition gives the wrong instruction
    ("conditions", "jab building dikhe tab ruk jana", (no, "condition")),
    ("conditions", "agar building dikhe to wahan ruko", (no, "condition")),
    ("conditions", "building dikhne par right le lo", (no, "condition")),
    ("conditions", "जब तक बिल्डिंग न दिखे सीधे आओ", (no, None)),
    # --- other people, other tenses
    ("someone else", "wo wahan ruka hua hai", (no, None)),
    ("someone else", "mera dost aa raha hai", (no, None)),
    ("someone else", "driver seedha aa raha hai", (no, "third_person")),
    ("someone else", "वो सीधे आ गया", (no, None)),
    # --- look-alikes and small talk
    ("look-alikes", "right side wala gate", (tr, [])),           # a landmark, not an instruction
    ("look-alikes", "सीधे हाथ की तरफ वाला मकान", (no, None)),
    ("look-alikes", "bhaiya thoda ruko, chai pi lo", (pa, [W])),
    ("look-alikes", "ok ok aa jao", (no, None)),
    ("look-alikes", "haan haan seedhe aa jao", (pa, [S])),
    # --- what the real Prisma wrote for a Hinglish voice (out/hinglish_prisma.json), Hindi mode
    ("real Prisma, Hindi mode", "भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी, वहाँ रुको मैं आ रहा हूँ।", (tr, [S, T, V, W, C])),
    ("real Prisma, Hindi mode", "स्ट्रेट आ जाओ फिर राइट टर्न कर लो।", (tr, [S, T])),
    ("real Prisma, Hindi mode", "वेट करो मैं आरो", (pa, [W])),                          # it garbled "aa raha hu"
    ("real Prisma, Hindi mode", "लेफ्ट साइड मत जाओ।", (no, None)),                      # it heard "mud jao" as "mat jao": refused, not reversed
    ("real Prisma, Hindi mode", "पहले लेफ्ट लो फिर राइट लो।", (tr, [T, T])),
    ("real Prisma, Hindi mode", "बिल्डिंग दिखने पर राइट ले लो।", (no, "condition")),
    ("real Prisma, Hindi mode", "दूसरे सिग्नल से लेफ्ट ले लो।", (no, None)),
    ("real Prisma, Hindi mode", "आप वहाँ वेट कीजिए मैं फाइव मिनट में आ रहा हूँ।", (pa, [W, C])),
    # --- the same sentences in English mode (Roman script)
    ("real Prisma, English mode", "bhaiya sidhe aa jao right le lo phir samne building dikhegi vahaan ruko mein aa raha hoon", (tr, [S, T, V, W, C])),
    ("real Prisma, English mode", "left side mudja", (tr, [T])),
    ("real Prisma, English mode", "pahle left lo phir right lo", (tr, [T, T])),
    ("real Prisma, English mode", "building dikhne per right le lo", (no, "condition")),
    ("real Prisma, English mode", "go straight and take a right", (tr, [S, T])),
]


def actual(text):
    r = translate(text, "hi-IN", "en")
    if r.status == "untranslated":
        return r, (no, r.reason)
    return r, (r.status, r.clauses)


def matches(expected, got):
    kind, what = expected
    if kind == no:
        return got[0] == no and (what is None or got[1] == what)
    return got == expected


def run():
    rows = []
    for group, text, expected in CASES:
        r, got = actual(text)
        rows.append({"group": group, "text": text, "expected": expected, "got": got, "english": r.english, "untranslated": r.untranslated,
                     "ok": matches(expected, got)})
    return rows


if __name__ == "__main__":
    rows = run()
    for r in rows:
        print(f"{'  ' if r['ok'] else '!!'} [{r['group']}] {r['text']}\n      expected {r['expected']}   got {r['got']}"
              f"{' | ' + r['english'] if r['english'] else ''}{' | not understood ' + str(r['untranslated']) if r['untranslated'] else ''}")
    print(f"\n{sum(r['ok'] for r in rows)} of {len(rows)} cases behave as expected")
