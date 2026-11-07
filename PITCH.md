# Solution pitch: Landmark Chain

**A prototype for the Great Indian AI Internship Challenge (Gnani AI).** Synthetic voices only. One page.

## The problem

A delivery rider and a customer often do not share a language, and the address is often a landmark ("behind the temple, blue gate") given over a call, not a pin on a map. A rider who hears Hindi they do not follow, or a customer who hears Kannada they do not follow, loses minutes on a call that was meant to end the delivery. We did not measure how often this causes a failed delivery, so we make no such claim; this is a hypothesis from the problem's shape.

## The solution

A **live call interpreter** between two phone-style windows. The customer speaks Hindi or Hinglish (or English), the rider hears Kannada (or English), and the rider's reply comes back the same way. Each window only ever receives its own language.

```
speaker's voice -> Gnani Prisma (speech to text) -> rules -> Gnani Timbre (text to speech) -> the other window only
```

The **translation step is rule-based**: fixed tables for landmarks, colours, lane numbers, sides, yes/no, and a closed grammar of seven direction clauses ("come straight, take a right, you will see a building ahead, wait there, I am coming"). It does not guess. **Anything it cannot translate is refused out loud, in both languages**, so nobody is sent the wrong way by a plausible-sounding mistake.

An **optional AI fallback** (Gnani's open-weight Evon, self-hosted) can be asked when the rules refuse a casual sentence. Its answer is spoken only if a fixed check finds left/right, negation, questions, conditions, colours and numbers matching what was said, and every such turn is labelled on screen. It is off in the main demo.

## What was built and checked

- Two caller windows, an operator view with timings, a scripted call, and a microphone mode (for your own voice, not for the contest video).
- Three language pairs through one pipeline: Hindi to Kannada, Kannada to Hindi, English to Hindi.
- 79 Hinglish edge cases with the correct outcome written down first, enforced by tests.
- The translated turn is ready about one to two seconds after the speaker stops. It is **not streaming**.
- Every number in `README.md` and `SUBMISSION.md` is generated from the saved result files in `out/`, and a test fails if the documents drift from the data.

## Honest limits

It covers landmarks and a few set directions only. Prisma can mishear a word under (simulated) bike noise, and the rules then refuse rather than guess. The Kannada wording was drafted without a native-speaker review (`kannada_review.md` lists every string for one). The AI check cannot catch a misheard transcript or every change of meaning. No rider or delivery company has been asked whether they want this.

## Run it

```
pip install -r requirements.txt        # then put GNANI_API_KEY in .env (see .env.example)
python live_call.py                     # open http://127.0.0.1:8770/
python -m unittest discover -s tests    # the tests
```

Details, results and the full list of Gnani models and APIs used: `README.md` and `SUBMISSION.md`.
