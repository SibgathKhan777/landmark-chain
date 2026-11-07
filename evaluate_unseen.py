"""Recall and false values of the extractor on the saved phrase sets. Offline, no API calls.

Sets A and B were measured BEFORE the lexicon was extended (68% and 47%); the lexicon was then extended using what they
missed, so their current numbers are in-sample. Only set C was never used for tuning.
"""
import sys

from extraction import CRITICAL, extract
from heldout import SETS


def measure(phrases, verbose=False):
    want_n = ok_n = fp_n = dropped = 0
    for phrase, want in phrases:
        e = extract(phrase)
        got = {k: set(v) for k, v in e.items() if k in CRITICAL and v}
        w = sum(len(v) for v in want.values())
        ok = sum(len(want[k] & got.get(k, set())) for k in want)
        fp = sum(len(got[k] - want.get(k, set())) for k in got)
        want_n, ok_n, fp_n, dropped = want_n + w, ok_n + ok, fp_n + fp, dropped + (not got)
        if verbose and (ok != w or fp):
            print(f"    found {ok}/{w}, false {fp}: {phrase}")
    return dict(phrases=len(phrases), wanted=want_n, found=ok_n, recall=round(100 * ok_n / want_n), false_values=fp_n, dropped=dropped)


def main():
    for name, note, phrases in SETS:
        m = measure(phrases, verbose="-v" in sys.argv)
        print(f"set {name} ({note}): {m['phrases']} phrases | critical values found {m['found']}/{m['wanted']} ({m['recall']}%) "
              f"| false values {m['false_values']} | phrases dropped {m['dropped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
