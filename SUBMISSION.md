# Landmark Chain: submission draft

> A draft for the Great Indian AI Internship Challenge submission. Result numbers are generated from the real result files by `python build_docs.py`. Sections marked **[EDIT]** need your own facts; do not submit them unchanged.

## One line

A live call between two windows: a customer who speaks Hindi and a biker who hears Kannada (or English) talk through an interpreter that translates landmark phrases and a small closed set of directions ("come straight, take a right, you will see a building ahead, wait there, I am coming"), and refuses out loud anything it cannot translate.

## The problem

The project starts from the observation that addresses are often given as landmarks ("behind the temple, blue gate") and not as exact addresses. We did not measure how often that causes a failed delivery; third-party logistics blogs say vague addresses are a leading cause, and we did not verify their figures. Landmark Chain captures the landmarks by voice once, merges what several customers said, and guides the rider by voice. This is a prototype of that flow; it has not been tested with real customers or riders.

## What I built

**1. A live call interpreter with two caller windows.** Each person has their own phone-style window; each window receives audio and captions only in its own language (Hindi or Kannada) or English. Prisma turns the speaker's audio into text, rules translate it, and Timbre speaks the result to the other window. By default there is no language model and no machine translation (an optional AI fallback is described below and is off in every recorded result): the rules cover landmark phrases (built from 15 landmark types, 6 relations, 9 colours, 5 lane or floor numbers, 2 sides, 8 things to point at), seven direction and plan clauses (come or go straight, turn left or right, "you will see X ahead", wait there, "I am coming", "I am standing here", "I can see the building") and 5 set phrases. Everything else is refused in both people's languages, and a partial translation is announced as partial. It has been run as a scripted call between synthetic voices, not on a real phone line. It is not streaming: the translation starts when the speaker stops talking.

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

**The live call.** A scripted call of 4 turns between synthetic voices through the real pipeline (simulated phone-line noise on the customer, bike noise at 5 dB on the biker): 1 translated, 1 partly translated, 2 not translated.

| Turn | Speaker | Said (synthetic voice) | Prisma heard | Result | The other window received | Ready after |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Customer (Hindi) | `भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ` | `भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ` | translated | `ನೇರವಾಗಿ ಬನ್ನಿ, ಬಲಕ್ಕೆ ತಿರುಗಿ, ಎದುರು ಕಟ್ಟಡ ಕಾಣಿಸುತ್ತದೆ, ಅಲ್ಲಿ ನಿಲ್ಲಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ` | 1.54 s |
| 2 | Biker (Kannada) | `ಕಟ್ಟಡ ಕಾಣಿಸಿತು` | `ಕಟ್ಟಡ ಕಾಣಿಸಿ` | not translated | a spoken notice that it could not translate | 1.72 s |
| 3 | Customer (Hindi) | `भैया मैं पांच मिनट में आ रहा हूँ` | `भैया मैं पाँच मिनट में आ रहा हूँ।` | partly translated | `ನಾನು ಬರುತ್ತಿದ್ದೇನೆ` | 1.62 s |
| 4 | Customer (Hindi) | `भैया चाय पीकर आना` | `भैया चाय पीकर आना` | not translated | a spoken notice that it could not translate | 1.97 s |

Ready after (from the end of the utterance to the translated audio being ready, measured on the machine running the server, over the internet, REST calls): median 1.72 s, fastest 1.54 s, slowest 1.97 s over 4 turns. Prisma took a median of 0.21 s and Timbre a median of 1.51 s; the rules took under 5 ms. The slowest turns are the refusals, because two spoken notices are synthesised one after the other.

The same script with the bike at 10 dB instead of 5 dB (a separate run, `results_bike10.json`, not a re-roll of the first): 2 translated, 1 partly translated, 1 not translated; the results differ from the first run in turn 2.

The biker's turn 2 (`ಕಟ್ಟಡ ಕಾಣಿಸಿತು`) came back from Prisma as `ಕಟ್ಟಡ ಕಾಣಿಸಿ` under 5 dB bike noise, and the interpreter refused it out loud in both languages instead of guessing. That is the intended behaviour, and also a real limit.

**Hinglish.** 79 Hinglish cases (Roman and Devanagari script, English words, misspellings, two-step routes, negations, questions, conditions, other people, distances, and transcripts that real Prisma returned for a Hinglish voice) each have the correct outcome written down first: 37 translate fully, 6 are partly translated with harmless words left out, 36 are refused. 79 of 79 behave as written (`experiments/hinglish_edge_cases.py`; a test enforces it). Testing found cases where a partial translation had dropped a condition or turned a question into an instruction; those are now refused, and a test keeps them that way.

**The optional AI fallback.** The rules refuse free description such as "the guy in the blue T-shirt will be visible". With `LLM_BASE_URL` set, the app asks Evon only after the rules fail, and speaks its answer only if a fixed check finds left/right, negation, question, condition, colours, numbers and (for standing, coming and "where") who does it matching what was said; those turns are labelled AI translated on screen. With the AI on, a rules fragment is spoken alone only if the rules understood at least nine in ten of the words. Measured on Kaggle: 18 sentences, English median 0.61 s, slowest 1.93 s; Kannada median 0.66 s, slowest 1.91 s. The guard accepted 17 of 18 Kannada answers and 15 of 18 English answers. **Through a real tunnel, with the prompt as amended after the live test below** (the same 18 sentences, sent from this Mac to the Kaggle server over a temporary public address, `out/evon_tunnel_test.json`): Kannada 17 accepted, 1 rejected, 0 errors, median 1.11 s (slowest 2.44 s); English 17 accepted, 1 rejected, 0 errors, median 1.13 s (slowest 1.68 s). A wrong key was refused with HTTP 401. The model's answers change when the prompt changes (with the earlier prompt the same test accepted fewer English answers), so these counts describe this prompt on this day, not the model. **The live sentences** (said into the app, then replayed with the amended prompt, `out/evon_live_sentences.json`): 5 sentences about who is standing or asking "where"; Kannada 3 accepted and 2 rejected; English 4 accepted and 1 rejected. The rejected ones are the model swapping the two people again, or dropping a question, which is what the check is for. **The scripted call with the fallback on** (`out/live/results_ai.json`, real Prisma and Timbre, real model over the tunnel): turn 1 translated, ready after 1.20 s; turn 2 untranslated, ready after 1.87 s; turn 3 AI translated (the rules had said partial; model answered in 1.25 s), ready after 2.02 s; turn 4 AI translated (the rules had said untranslated; model answered in 1.05 s), ready after 1.69 s. **Kannada replies** (`out/evon_kannada_source.json`, 7 Kannada sentences, each to Hindi and English through the tunnel): 6 Hindi and 6 English answers passed the check, 1 Hindi and 1 English were rejected (all for the one sentence that was a misheard transcript: `ಎಲ್ಲದ ಬ್ರೋ ನಾನು ಇಲ್ಲದ`).

**A realistic delivery call** (`python live_call.py --run --script real`; the AI fallback ON and its check ON; the rider's noise 10 dB, the quieter of two runs, saved in `out/live/results_real_bike10.json`). Arun asks where the rider is, Manju is lost, Arun gives directions, Manju sees the building, Arun says where he is, Manju is on the way. Median ready after 2.02 s.

| Turn | Speaker | Said (synthetic voice) | Prisma heard | Result | The other person hears | Ready after |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Arun (customer, Hindi) | `हेलो भैया, आप कहाँ हो?` | `हेलो भैया आप कहाँ हो` | AI translated | `ನಮಸ್ಕಾರ ಅಣ್ಣಾ, ನೀವು ಎಲ್ಲಿ ಇದ್ದೀರಿ?` | 2.20 s |
| 2 | Manju (rider, Kannada) | `ಅಣ್ಣಾ ನಾನು ಮುಖ್ಯ ರಸ್ತೆಯಲ್ಲಿ ಇದ್ದೀನಿ, ಅಡ್ರೆಸ್ ಸಿಗ್ತಿಲ್ಲ` | `ಅಣ್ಣ ನಾನು ಮುಖ್ಯ ರಸ್ತೆಯಲ್ಲಿ ಇದ್ದೀನಿ ಅಡ್ರೆಸ್ ಸಿಗ್ತಿಲ್ಲ` | AI translated | `भाई, मैं मुख्य सड़क पर हूँ पता नहीं मिल रहा।` | 1.89 s |
| 3 | Arun (customer, Hindi) | `भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ` | `भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ` | translated by the rules | `ನೇರವಾಗಿ ಬನ್ನಿ, ಬಲಕ್ಕೆ ತಿರುಗಿ, ಎದುರು ಕಟ್ಟಡ ಕಾಣಿಸುತ್ತದೆ, ಅಲ್ಲಿ ನಿಲ್ಲಿ, ನಾನು ಬರುತ್ತಿದ್ದೇನೆ` | 1.13 s |
| 4 | Manju (rider, Kannada) | `ಕಟ್ಟಡ ಕಾಣಿಸಿತು ಅಣ್ಣಾ` | `ಕಟ್ಟಡ ಕಾಣಿಸಿತು ಅಣ್ಣ` | translated by the rules | `बिल्डिंग दिख गई` | 0.67 s |
| 5 | Arun (customer, Hindi) | `हाँ वही है, मैं तीसरे फ्लोर पर हूँ, नीला दरवाजा है` | `हाँ वही है मैं तीसरे फ्लोर पर हूँ नीला दरवाज़ा है` | AI translated | `ಹೌದು ಅದೇ ಇದೆ, ಮೂರನೇ ಮಹಡಿಯಲ್ಲಿದ್ದೇನೆ ನೀಲಿ ಬಾಗಿಲು ಕಾಣಿಸುತ್ತದೆ.` | 3.16 s |
| 6 | Manju (rider, Kannada) | `ಸರಿ ಅಣ್ಣಾ, ಬರ್ತಾ ಇದ್ದೀನಿ` | `ಸರಿ ಅಣ್ಣ ಬರ್ತಾಯಿದ್ದೀನಿ` | AI translated | `ठीक है, भाई आ रहा हूँ।` | 2.02 s |

**The same call at 5 dB** (`out/live/results_real.json`), where a rider's line is misheard:
- **5 dB, turn 2:** Prisma wrote `ಅಣ್ಣ ಅಕ್ಕ ನಾನು ಮುಖ್ಯರಸ್ತೆಯಲ್ಲಿದ್ದೀನಿ ಆಕ್ಕ ಅಡ್ರೆಸ್ ಸಿಕ್ತಿಲ್ಲ` for `ಅಣ್ಣಾ ನಾನು ಮುಖ್ಯ ರಸ್ತೆಯಲ್ಲಿ ಇದ್ದೀನಿ, ಅಡ್ರೆಸ್ ಸಿಗ್ತಿಲ್ಲ`, and the AI faithfully translated that to `भाई, बहन और मैं मुख्य सड़क पर हूँ। माँ को पता नहीं मिल रहा है।` (AI translated), which the check let through, because it cannot know a transcript was misheard. 
- **5 dB, turn 4:** Prisma wrote `ಕಟ್ಟಡ ಕಾಣಿಸಿತು ಅಣ್ಣ` for `ಕಟ್ಟಡ ಕಾಣಿಸಿತು ಅಣ್ಣಾ`, and the AI faithfully translated that to `बिल्डिंग दिख गई`. 
- **5 dB, turn 6:** Prisma wrote `ಸರಿ ಅಣ್ಣ ಬರ್ತಾಯಿದ್ದೀನಿ` for `ಸರಿ ಅಣ್ಣಾ, ಬರ್ತಾ ಇದ್ದೀನಿ`, and the AI faithfully translated that to `ठीक है, भाई आ रहा हूँ।` (AI translated), which the check let through, because it cannot know a transcript was misheard. 

**A second language pair: the customer speaks English and the rider speaks Hindi** (`python live_call.py --run --script english`; rules only, no AI; the rider's noise 5 dB; saved in `out/live/results_english.json`). The English side is a small grammar of its own: go or come straight, turn or take a left or right, "you will see a (colour) building ahead", wait here or there, plus yes, no, found it and could not find it. Median ready after 1.00 s.

| Turn | Speaker | Said (synthetic voice) | Prisma heard | Result | The other person hears | Ready after |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Arun (customer, English) | `Go straight, take a right, then you will see a building ahead. Wait there.` | `go straight take a right then you will see a building ahead wait there` | translated | `सीधे जाइए, दाएं मुड़िए, सामने बिल्डिंग दिखेगी, वहाँ रुकिए` | 1.00 s |
| 2 | Manju (rider, Hindi) | `बिल्डिंग दिख गई भैया` | `बिल्डिंग दिख गई भैया` | translated | `I can see the building` | 0.86 s |
| 3 | Arun (customer, English) | `Wait there, I will be down in five minutes.` | `wait there i will be down in five minutes` | partly translated | `वहाँ रुकिए` | 0.99 s |
| 4 | Arun (customer, English) | `Please bring some water.` | `please drink some water` | refused | a spoken notice | 1.45 s |

Not covered: the AI fallback has no English-to-Hindi route, so English that the rules cannot read is refused or translated in part; "I am coming" and "I am standing" are not read in English (the Hindi side does read them); and the Hindi wording was written by me and not reviewed by a native speaker. Prisma wrote `please drink some water` for `Please bring some water.` in turn 4 (refused).

`demos/` holds a saved copy of the realistic call: 6 turns recorded with the rider's noise at 10 dB, including the 4 answers the AI gave (each passed the check when recorded), and 9 synthetic speaker clips (650 KB). `python live_call.py --biker-snr 10 --replay-ai` plays it with **no model running**: Prisma and Timbre are still called live, the AI answers come from the file and every such turn is labelled **AI translated, recorded answer**, and the check still runs on them. In replay mode the AI can answer only the sentences of that recorded call; anything else is refused as without the AI. The model swapped left and right once and dropped "two" from "after two lanes", both fluently, and the guard (written after seeing them) catches both. A live test found a wrong answer that passed the first version of the check (the two people swapped in "where are you, I am standing here"); the check now covers who is standing, coming or "where", but not who does anything else, so AI turns are labelled "not fully checked". The Kannada has not been reviewed by a native speaker.

**The earlier recorded replay** (`call_demo.py`): 6 turns, 4 translated, 1 partly translated, 1 not translated.

| Turn | Speaker | Said | Prisma heard | Interpreter | The other person hears |
| --- | --- | --- | --- | --- | --- |
| 1 | Customer (Hindi) | `भैया ये गेट दूसरा गेट दायीं तरफ वाला` | `भैया ये गेट दूसरा गेट दायीं तरफ वाला` | translated | `ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್` |
| 2 | Biker (Kannada) | `ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್` | `ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್` | translated | `दाएं तरफ दूसरा गेट` |
| 3 | Customer (Hindi) | `हाँ, सही है` | `हाँ सही है` | translated | `ಹೌದು, ಸರಿ` |
| 4 | Biker (Kannada) | `ಸಿಕ್ಕಿತು` | `ಸಿಕ್ಕಿತು` | translated | `मिल गया` |
| 5 | Customer (Hindi) | `भैया मैं पांच मिनट में आ रहा हूँ दूसरा गेट दायीं तरफ` | `भैया मैं पाँच मिनट में आ रहा हूँ, दूसरा गेट दाईं तरफ।` | partly translated | `ನಾನು ಬರುತ್ತಿದ್ದೇನೆ, ಬಲಗಡೆಯ ಎರಡನೇ ಗೇಟ್` |
| 6 | Customer (Hindi) | `भैया चाय पीकर आना` | `भैया चाय पीकर आना।` | not translated | a spoken notice that it could not translate |

Every phrase the tables can write in Hindi and in Kannada was spoken by Timbre and transcribed by Prisma in clean conditions, and the meaning survived:

| Language | Phrases | Same meaning after speech and recognition | Identical text |
| --- | --- | --- | --- |
| Hindi | 14 | 14 of 14 | 13 of 14 |
| Kannada | 14 | 14 of 14 | 12 of 14 |

**Route memory and rider confirmation.**

All figures use synthetic Timbre speech and simulated noise, each from one sample. Full tables and caveats are in `README.md`.

- Across the recorded noise sweeps, look-alike transcripts accepted as the wrong landmark: **0**. This applies to those phrase groups only.
- Replayed recorded transcripts from the 24-phrase sweep, checked against what was spoken: 124 accepted, 18 read-back, 1 ask-again, 1 mismatch of 144.
- In the demo, 4 customers (Hindi and Marathi) merged into one route, and the rider (a synthetic Marathi voice) confirmed each landmark through simulated bike noise:

| Step | Landmark | Noise | Outcome |
| --- | --- | --- | --- |
| 1 | देवळाच्या मागे | bike 10 dB | CONFIRMED by voice after 1 try |
| 2 | निळे गेट | bike 5 dB | CONFIRMED by voice after 1 try |
| 3 | हिरवे घर | bike 0 dB | CONFIRMED by voice after 1 try |

- The same landmark in four noise conditions. Background speech was the hard case, and the bot asked again instead of guessing:

| Condition | Prisma heard | Decision |
| --- | --- | --- |
| bike@10 | `मला निळे गेट दिसले` | ACCEPT (all_slots_matched) |
| bike@5 | `मला निळे गेट दिसले` | ACCEPT (all_slots_matched) |
| bike@0 | `मला निळे गेट दिसले का` | ACCEPT (all_slots_matched) |
| babble@5 | `मला निर्णय घेत` | ASK_AGAIN (nothing_matched) |

- At 5 dB, exact match was 79% with engine hum alone and 50% with babble alone, on the same phrasings.
- Timbre returns different audio on identical requests while Prisma returns the same transcript for identical audio, so results from a re-run differ somewhat.

## What it does not do

- It has not been tried with real customers, riders, phones, accents or traffic. The call is scripted; the microphone button exists but has not been used by a real person, and it would send that person's voice to Gnani.
- It takes about 1 to 2 seconds after a speaker stops before the other window starts speaking (measured, varies run to run). It is not instant and not streaming.
- The interpreter refuses everything outside its tables: ordinary conversation, times and numbers, directions that start from a landmark, conditions ("when you see the building, turn"), distances and counts, statements about someone else, questions, "not the blue gate" or "do not turn", two values at once, several landmarks in one breath, and landmarks it has never seen. A misheard word is translated faithfully, so the biker's read-back is what catches it.
- The Kannada wording was drafted without a native-speaker review (`kannada_review.md`).
- Extraction is a closed word list. On fresh phrases it found 35/43 (81%) of the critical words, and misses landmark nouns it has not seen.
- No read-back, ask-again or tap fallback happened in this run's live scenes. Those paths appear only in a replay of recorded cases, which the demo labels as replayed.
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
