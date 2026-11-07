"""Text normalisation shared by extraction, verification and evaluation."""
import unicodedata

PUNCT = "।,.?!-–\"'()"


def norm(s):
    """NFC, drop nukta, fold ऱ/ऩ/ऴ to plain letters, chandrabindu -> anusvara, strip punctuation."""
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("़", "").replace("ँ", "ं")
    s = s.replace("ऱ", "र").replace("ऩ", "न").replace("ऴ", "ळ")
    for ch in PUNCT:
        s = s.replace(ch, " ")
    return " ".join(s.lower().split())


def tokens(s):
    return norm(s).split()
