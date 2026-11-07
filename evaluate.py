"""Replay the real Prisma transcripts from the noise sweeps through the verifier (no API calls).

Own:   transcript of phrase X verified against X      -> how often the rider is accepted / asked again
Cross: transcript of phrase X verified against sibling Y -> must never be ACCEPT (false accept)
"""
import csv
import sys
from collections import Counter, defaultdict

from sweep import PHRASES as ORIG
from sweep2 import HARD
from verify import ACCEPT, ASK_AGAIN, CONFIRM, MISMATCH, verify

OUT = "out"
DEC = [ACCEPT, CONFIRM, ASK_AGAIN, MISMATCH]


def groups():
    g = {}
    for lang, gs in HARD.items():
        for name, items in gs.items():
            ps = [p for p, _, _ in items]
            for p in ps:
                g[p] = ps
    for lang, items in ORIG.items():
        ps = [p for p, _, _ in items]
        for p in ps:
            g.setdefault(p, ps)
    return g


def load(out_dir=OUT):
    rows = []
    for name, part in (("hard_results.csv", None), ("sweep_results.csv", "orig-white")):
        try:
            with open(f"{out_dir}/{name}", newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    kind = r.get("part") or part
                    r["set"] = "hard" if kind == "hard" else ("orig-bike" if kind == "orig" else "orig-white")
                    rows.append(r)
        except FileNotFoundError:
            pass
    return rows


def analyse(out_dir=OUT):
    """Returns (own, cross, false_accepts): per (set, condition) decision counters. No printing."""
    sib = groups()
    own, cross, false_acc = defaultdict(Counter), defaultdict(Counter), []
    for r in load(out_dir):
        key = (r["set"], r["cond"])
        own[key][verify(r["ref"], r["hyp"]).decision] += 1
        for other in sib.get(r["ref"], []):
            if other == r["ref"]:
                continue
            d = verify(other, r["hyp"]).decision
            cross[key][d] += 1
            if d == ACCEPT:
                false_acc.append((key, other, r["hyp"]))
    return own, cross, false_acc


ORDER = ["clean", "20dB", "10dB", "bike@10", "5dB", "bike@5", "engine@5", "babble@5", "0dB", "bike@0"]


def main():
    own, cross, false_acc = analyse()
    for s in ("hard", "orig-bike", "orig-white"):
        keys = [k for k in own if k[0] == s]
        if not keys:
            continue
        print(f"\n== {s}: own transcript vs its own landmark | sibling transcript vs wrong landmark")
        print(f"{'cond':<10}{'n':>4} {'ACCEPT':>7}{'CONFIRM':>8}{'ASK':>5}{'MISMATCH':>9} || {'pairs':>6} {'falseACC':>9}{'CONFIRM':>8}{'MISM':>6}{'ASK':>5}")
        for k in sorted(keys, key=lambda k: ORDER.index(k[1]) if k[1] in ORDER else 99):
            o, c = own[k], cross[k]
            n, m = sum(o.values()), sum(c.values())
            pct = lambda x, d: f"{round(100 * x / d)}%" if d else "-"
            print(f"{k[1]:<10}{n:>4} {pct(o[ACCEPT], n):>7}{pct(o[CONFIRM], n):>8}{pct(o[ASK_AGAIN], n):>5}{pct(o[MISMATCH], n):>9} || {m:>6} {c[ACCEPT]:>9}{pct(c[CONFIRM], m):>8}{pct(c[MISMATCH], m):>6}{pct(c[ASK_AGAIN], m):>5}")
    print(f"\nFalse accepts (sibling transcript accepted as the wrong landmark): {len(false_acc)}")
    for k, other, hyp in false_acc[:10]:
        print("  ", k, other, "<-", hyp)
    return 1 if false_acc else 0


if __name__ == "__main__":
    sys.exit(main())
