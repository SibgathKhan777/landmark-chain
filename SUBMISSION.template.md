# Landmark Chain: submission draft

> A draft for the Great Indian AI Internship Challenge submission. Result numbers are generated from the real result files by `python build_docs.py`. Sections marked **[EDIT]** need your own facts; do not submit them unchanged.

## One line

A live call between two windows: a customer who speaks Hindi and a biker who hears Kannada (or English) talk through an interpreter that translates landmark phrases and a small closed set of directions ("come straight, take a right, you will see a building ahead, wait there, I am coming"), and refuses out loud anything it cannot translate.

## The problem

The project starts from the observation that addresses are often given as landmarks ("behind the temple, blue gate") and not as exact addresses. We did not measure how often that causes a failed delivery; third-party logistics blogs say vague addresses are a leading cause, and we did not verify their figures. Landmark Chain captures the landmarks by voice once, merges what several customers said, and guides the rider by voice. This is a prototype of that flow; it has not been tested with real customers or riders.

## What I built

**1. A live call interpreter with two caller windows.** Each person has their own phone-style window; each window receives audio and captions only in its own language (Hindi or Kannada) or English. Prisma turns the speaker's audio into text, rules translate it, and Timbre speaks the result to the other window. By default there is no language model and no machine translation (an optional AI fallback is described below and is off in every recorded result): the rules cover landmark phrases (built from {{VOCAB_LINE}}), seven direction and plan clauses (come or go straight, turn left or right, "you will see X ahead", wait there, "I am coming", "I am standing here", "I can see the building") and {{PHRASEBOOK_N}} set phrases. Everything else is refused in both people's languages, and a partial translation is announced as partial. It has been run as a scripted call between synthetic voices, not on a real phone line. It is not streaming: the translation starts when the speaker stops talking.

**2. A route memory with rider confirmation**, a Python application with four parts plus a demo page:

1. **Capture:** customers' spoken descriptions are transcribed by Prisma and reduced by a rule-based extractor to language-neutral slots (anchor, relation, colour, ordinal, side).
2. **Store:** a SQLite store merges descriptions per pincode and locality into one route, with confidence that rises with evidence, falls on an explicit "not found" and fades with age.
3. **Guide:** Timbre reads the route to the rider in their language (a renderer turns slots back into Hindi or Marathi).
4. **Confirm:** the rider repeats each landmark. A word-level verifier accepts, asks for a read-back, flags a mismatch or asks again, and never picks the nearest candidate when unsure. After three failed attempts the rider is offered a button.

## Gnani AI models and APIs used

| Model | How it is used |
|---|---|
| **Prisma v2.5** (speech to text) | REST `POST /stt/v3`. Languages `hi-IN` and `kn-IN` in the call interpreter, `hi-IN` and `mr-IN` in the route memory; `en-IN` in the smoke test. Transcribes customers describing a house and the rider confirming landmarks |
| **Timbre v2.5** (text to speech) | REST `POST /api/v1/tts/inference`. Voices Nalini and Deepak (Hindi), Kavin and Saanvi (Kannada), Zahira and Ishaan (Marathi), Poorvi (Hinglish, smoke test only). Speaks the bot's prompts, and generates every synthetic customer and rider voice used for testing |

Not used: Warp, voice cloning, streaming or batch speech-to-text, the streaming Timbre endpoints (only measured once), and no external translation or language-model service. **Evon** (Gnani's open-weight model, self-hosted, not on Gnani's API) was tested and is wired in as an optional fallback that is off in every recorded result. Gnani's account allows one active request at a time, so the app serialises every call.

## What the results show

**The live call.** A scripted call of {{LIVE_N}} turns between synthetic voices through the real pipeline (simulated phone-line noise on the customer, bike noise at {{LIVE_SNR}} dB on the biker): {{LIVE_COUNTS}}.

{{LIVE_TABLE}}

{{LIVE_LATENCY}}

{{LIVE_QUIETER}}

{{LIVE_BIKER_NOTE}}

**Hinglish.** {{HINGLISH_LINE}} Testing found cases where a partial translation had dropped a condition or turned a question into an instruction; those are now refused, and a test keeps them that way.

**The optional AI fallback.** The rules refuse free description such as "the guy in the blue T-shirt will be visible". With `LLM_BASE_URL` set, the app asks Evon only after the rules fail, and speaks its answer only if a fixed check finds left/right, negation, question, condition, colours, numbers and (for standing, coming and "where") who does it matching what was said; those turns are labelled AI translated on screen. With the AI on, a rules fragment is spoken alone only if the rules understood at least nine in ten of the words. Measured on Kaggle: {{EVON_N}} sentences, {{EVON_TIMES}}. {{EVON_GUARD_LINE}} {{EVON_TUNNEL}} {{EVON_E2E}} {{EVON_KN}}

{{LIVE_REAL}}

{{LIVE_ENGLISH}}

{{DEMO_SAVED}} The model swapped left and right once and dropped "two" from "after two lanes", both fluently, and the guard (written after seeing them) catches both. A live test found a wrong answer that passed the first version of the check (the two people swapped in "where are you, I am standing here"); the check now covers who is standing, coming or "where", but not who does anything else, so AI turns are labelled "not fully checked". The Kannada has not been reviewed by a native speaker.

**The earlier recorded replay** (`call_demo.py`): {{CALL_N}} turns, {{CALL_COUNTS}}.

{{CALL_TABLE}}

Every phrase the tables can write in Hindi and in Kannada was spoken by Timbre and transcribed by Prisma in clean conditions, and the meaning survived:

{{ROUNDTRIP_TABLE}}

**Route memory and rider confirmation.**

All figures use synthetic Timbre speech and simulated noise, each from one sample. Full tables and caveats are in `README.md`.

- Across the recorded noise sweeps, look-alike transcripts accepted as the wrong landmark: **{{FALSE_ACCEPTS}}**. This applies to those phrase groups only.
- Replayed recorded transcripts from the 24-phrase sweep, checked against what was spoken: {{REPLAY_LINE}}.
- In the demo, {{N_CUSTOMERS}} customers ({{LANGS}}) merged into one route, and the rider (a synthetic Marathi voice) confirmed each landmark through simulated bike noise:

{{STEPS_TABLE}}

- The same landmark in four noise conditions. Background speech was the hard case, and the bot asked again instead of guessing:

{{LADDER_TABLE}}

- {{NOISE_COMPARE}}
- Timbre returns different audio on identical requests while Prisma returns the same transcript for identical audio, so results from a re-run differ somewhat.

## What it does not do

- It has not been tried with real customers, riders, phones, accents or traffic. The call is scripted; the microphone button exists but has not been used by a real person, and it would send that person's voice to Gnani.
- It takes about 1 to 2 seconds after a speaker stops before the other window starts speaking (measured, varies run to run). It is not instant and not streaming.
- The interpreter refuses everything outside its tables: ordinary conversation, times and numbers, directions that start from a landmark, conditions ("when you see the building, turn"), distances and counts, statements about someone else, questions, "not the blue gate" or "do not turn", two values at once, several landmarks in one breath, and landmarks it has never seen. A misheard word is translated faithfully, so the biker's read-back is what catches it.
- The Kannada wording was drafted without a native-speaker review (`kannada_review.md`).
- Extraction is a closed word list. On fresh phrases it found {{EXTRACTOR_C}} of the critical words, and misses landmark nouns it has not seen.
- {{LIVE_PATHS}} Those paths appear only in a replay of recorded cases, which the demo labels as replayed.
- The AI fallback is optional, needs Evon hosted somewhere (Gnani has no hosted language-model API), was tested only on one run of 18 sentences, and its check covers only the listed details. Any video that turns it on must say so, and `LLM_GUARD=off` (AI answers spoken even if the check rejects them, labelled NOT checked) must not be used for the video.
- Prisma gives no confidence score, so uncertainty is inferred from the transcript.
- No buyer has said they would pay for this.

## Who it could help (a hypothesis)

Last-mile delivery operators and online sellers whose customers give landmark-style addresses. This has not been validated with any of them.

## Team and contributions **[EDIT]**

Team size: **[solo or two]**.

| Person | What they did |
|---|---|
| **[Your name, college]** | **[Write what you personally did, in your own words. For example: chose the problem; decided what to measure; ran and interpreted the experiments; recorded and posted the demo]** |
| **[Teammate, if any]** | **[Their contribution. Each person is assessed individually at interview]** |

**How AI tools were used [EDIT to match what is true]:** the code, tests and documents were written with the help of an AI coding assistant, working from decisions and direction given by the team. Be ready to explain every module, since interviews are individual.

## Data statement

All audio is generated by Gnani Timbre and all noise is simulated. No real phone numbers, account numbers, Aadhaar, PAN, recordings or personal data are used.

## Demo post draft **[EDIT]**

> Customers give directions in Hindi; riders think in Kannada. I built a call between two windows: the customer says "come straight, take a right, you will see a building ahead", Prisma hears them, and the biker's window speaks it in Kannada through Timbre. It only translates landmarks and a few set directions, and when it can't, it says so out loud instead of guessing. Built on Gnani AI's Prisma and Timbre. All voices are synthetic, the noise is simulated, and the Kannada has not yet been reviewed by a native speaker.
> **[Tag Gnani AI's official account here]** #GnaniAI #GreatIndianAIInternshipChallenge

## Submission checklist, from the contest terms

- [ ] Public demo video posted on LinkedIn and/or X, explaining what was built and which Gnani technology it uses
- [ ] Gnani AI's official account tagged, and both hashtags included
- [ ] The post is live **before** you submit; nominate one post per platform
- [ ] Written project explanation (this document), Gnani models or APIs used, and the post links submitted through the programme page by **10 November 2026, 11:59 PM IST**
- [ ] Only synthetic data; no purchased or exchanged engagement
- [ ] The **[EDIT]** sections above filled in truthfully
