"""Live check (about 10 API calls): do Timbre prompts render, and do spoken yes/no replies parse?"""
import gnani
from checkpoint import PROMPTS, parse_yes_no

OUT = gnani.HERE / "out"
EXP = {"hi-IN": ("मंदिर के पीछे नीला गेट", "Nalini"), "mr-IN": ("देवळाच्या मागे निळे गेट", "Zahira")}

for lang, (phrase, voice) in EXP.items():
    text = PROMPTS[lang]["confirm"].format(p=phrase)
    wav = gnani.tts(text, voice, lang)
    (OUT / f"prompt_confirm_{lang}.wav").write_bytes(wav)
    print(f"[ok] Timbre {lang} confirm prompt: {text}")

REPLIES = [("hi-IN", "हाँ", "yes"), ("hi-IN", "नहीं", "no"), ("mr-IN", "हो", "yes"), ("mr-IN", "नाही", "no")]
for lang, said, want in REPLIES:
    voice = EXP[lang][1]
    heard = gnani.stt(gnani.tts(said, voice, lang), lang)
    got = parse_yes_no(heard)
    print(f"[{'ok' if got == want else 'FAIL'}] said {said!r} -> Prisma {heard!r} -> {got} (want {want})")
