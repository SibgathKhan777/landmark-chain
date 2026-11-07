# Landmark Chain: five short ads

Written with the `yt-shorts` skill. That skill normally cuts Shorts out of a long video's transcript; there is no long video here, so each ad is built from a real moment of the saved demo calls instead (`out/live/results*.json`, `demos/`). Nothing here publishes anything: you record, you post.

**Every ad must carry this, on screen the whole time (the 9:16 crop removes the page's badges, so put it back in a caption):** `Prototype · synthetic voices · Kannada not yet reviewed by a native speaker`. The contest asks for synthetic data only, and the 60-second entry video's own rules (`RECORDING_PLAN.md`, "What not to claim") apply to these too.

Hook scores are from `hookscore.py`. It separates bad hooks from real ones, and barely separates a creator's own hits from misses, so a "WEAK" is a reason to look again and "WORKABLE" is not a promise. Four of the five scored WEAK (42 to 53); the ranking below is by score except where noted.

| Rank | Ad | Spoken first line | Hook score |
|---|---|---|---|
| 1 | The lost rider | "Your rider is lost, and doesn't speak your language. Watch what happens next." | 55 WORKABLE |
| 2 | The swapped turn | "Before your rider turns, we check the AI didn't swap left and right." | 53 WEAK |
| 3 | Five directions | "You say 5 directions in Hindi. Your rider hears Kannada in under 2 seconds." | 52 WEAK |
| 4 | English to Hindi | "Your customer speaks English, your rider speaks Hindi. 4 turns, under 2 seconds each." | 51 WEAK |
| 5 | The noisy bike | "Your rider is on a noisy bike and the speech engine mishears. Watch what the app does." | 42 WEAK |

I would film **5 first even though it scored lowest**: it is the only ad that shows the product failing and handling it, which is the most believable thing in the set, and a score built on specifics and stakes cannot see that. It is your call.

---

## Ad 1: The lost rider (25 s)

- **Spoken first line:** "Your rider is lost, and doesn't speak your language. Watch what happens next."
- **On-screen text, first 2 s (different words):** `Lost. Wrong language.`
- **Footage:** the default scripted call, turn 1: the customer's Hindi sentence `भैया सीधे आ जाओ राइट ले लो फिर सामने बिल्डिंग दिखेगी वहाँ ठहरो मैं आ रहा हूँ` in the customer window, the Kannada caption and audio in the biker window.
- **Beats:** 0-4 s first line over the idle biker window · 4-16 s the turn plays, both captions visible · 16-22 s the biker's window shows the Kannada, then cut to the operator panel's English meaning as a caption · 22-25 s end card.
- **Last spoken line (loop point):** "Each person only hears their own language. Now watch it again." This sets up the first line, and the loop shows the same call from the start.
- **End card:** `Landmark Chain · built on Gnani Prisma and Timbre`
- **Vertical framing:** crop to the biker window (it is already portrait). The middle panel with the English meaning is lost in the crop, so burn the English in as a caption.
- **Claims and where they come from:** all five directions are translated in the saved run (`out/live/results.json`, turn 1: translated). "Each window only hears its own language" is enforced by the server and tested (`tests/test_live.py`).

## Ad 2: The swapped turn (30 s)

- **Spoken first line:** "Before your rider turns, we check the AI didn't swap left and right."
- **On-screen text:** `AI said left. Customer said right.` (this is the model's mistake from our test, shown as text, not as a live demo)
- **Footage:** the README's Evon result as a text card (the model wrote "the one on the left" for "right side"), then the realistic call (`--replay-ai`) with a turn labelled **AI translated, recorded answer**.
- **Beats:** 0-5 s hook · 5-14 s the text card of the mistake · 14-24 s a replayed AI turn, with its label visible · 24-30 s the caveat below, spoken.
- **Must say, plainly:** "In our test the model swapped left and right once. The check is a fixed comparison of left, right, no, questions, colours and numbers. We wrote it after seeing those mistakes, so we do not know how it does on new ones." (`README.md`, Evon section: the results are in-sample.)
- **Loop point:** end on "…so we do not know how it does on new ones." The first line then reads as the thing being tested.
- **Vertical framing:** the AI label sits in the caption row of the phone window, so keep it inside the crop.
- **Do not say:** that the AI is accurate, or that it never swaps directions. The replay mode must be named as recorded answers.

## Ad 3: Five directions (20 s)

- **Spoken first line:** "You say 5 directions in Hindi. Your rider hears Kannada in under 2 seconds."
- **On-screen text:** `straight · right · building · wait · coming`
- **Footage:** default call turn 1, with each direction highlighted in the English caption as it is spoken.
- **Beats:** 0-3 s hook · 3-15 s the turn, with the five directions ticking on screen · 15-20 s the timing figure on screen.
- **Claims and sources:** the sentence contains five clauses, all translated (`results.json` turn 1). "Under 2 seconds" is the saved run: the slowest of the four turns was 1.97 s, turn 1 took 1.55 s. This is the time until the translated audio was ready, not until it finished playing, and a re-run differs. Say "ready in" on screen, not "heard in". Not streaming: it starts after the speaker stops.
- **Loop point:** end on "…if it hears it right." and open with the first line again.
- **Do not say:** real-time, live phone line, or any accuracy figure.

## Ad 4: English to Hindi (20 s)

- **Spoken first line:** "Your customer speaks English, your rider speaks Hindi. 4 turns, under 2 seconds each."
- **On-screen text:** `English in. Hindi out.`
- **Footage:** `python live_call.py --biker-snr 10 --replay-ai`, then **Play English-Hindi call** (rules only, no AI). Turn 1 and turn 2 are the clean ones.
- **Beats:** 0-3 s hook · 3-10 s customer: "Go straight, take a right, then you will see a building ahead. Wait there." · 10-16 s the rider's Hindi `बिल्डिंग दिख गई भैया` becoming "I can see the building" · 16-20 s the refusal of "Please bring some water" with its spoken notice.
- **Claims and sources:** `out/live/results_english.json`: turns ready after 0.86 to 1.45 s; turn 4 is refused, and Prisma heard "bring" as "drink". Show that honestly or leave turn 4 out. It is rules only, no AI.
- **Loop point:** end on the refusal: "When it cannot translate, it says so." The first line then starts the next try.
- **Do not say:** that it understands English conversation. Its English covers a few directions and yes, no, found it.

## Ad 5: The noisy bike (25 s)

- **Spoken first line:** "Your rider is on a noisy bike and the speech engine mishears. Watch what the app does."
- **On-screen text:** `5 dB bike noise (simulated)`
- **Footage:** the default call at the default 5 dB: turn 2, the biker's `ಕಟ್ಟಡ ಕಾಣಿಸಿತು`, which Prisma wrote as `ಕಟ್ಟಡ ಕಾಣಿಸಿ`, and the app refused it out loud in both languages instead of guessing. Then the same call at 10 dB, where the turn is translated (`results_bike10.json`, a separate run, not a re-roll).
- **Beats:** 0-5 s hook · 5-14 s the 5 dB refusal with the spoken notice · 14-21 s the 10 dB run translating the same line · 21-25 s the closing line.
- **Must say:** "The noise is simulated. This is a single sample on synthetic voices." (`RECORDING_PLAN.md`: no accuracy numbers.)
- **Loop point:** end on "Better to say 'I can't' than to send you the wrong way." The first line then answers it.
- **Do not say:** that it works in traffic, or that the 10 dB run is a better take of the same test.

---

## Common to all five

- **Voice-over:** read the spoken lines yourself or use a synthetic voice, but a real person's voice must not go through the app's microphone button, because the contest asks for synthetic data only. The narrator's voice is not sent to Gnani; only the app's input is.
- **Computer audio:** capturing the Mac's own audio needs extra software or a recent OBS, and I have not tested it on your machine. Without it the clips have captions and no Hindi or Kannada sound.
- **Do not re-run until a turn comes out the way you like.** Film what the saved run shows.
- **Not to be claimed in any ad:** "real-time", "streaming", "Gnani translates" (Gnani provides Prisma and Timbre; the translation step is ours), that riders or delivery companies want it, that it solves failed deliveries, "first", "only", "best", "no AI" (Prisma and Timbre are AI models; only the translation step uses fixed tables, or the optional AI fallback when it is on).
- **Contest post (not the ads):** the contest rules in `RECORDING_PLAN.md` ask for a tag of Gnani AI's official account on the entry post; the ads do not need one. Use #GnaniAI #GreatIndianAIInternshipChallenge. Submissions close 10 November 2026, 11:59 PM IST.

## Copy-and-paste post lines (one per ad)

1. `Your rider is lost and doesn't speak your language. A scripted demo call: Hindi in, Kannada out, built on Gnani Prisma and Timbre. Prototype, synthetic voices, Kannada not yet reviewed by a native speaker. #GnaniAI #GreatIndianAIInternshipChallenge`
2. `An AI swapped left and right in our test. A fixed check now compares left, right, no, questions, colours and numbers before anything is spoken. Written after seeing the mistakes, so unseen ones are untested. Prototype, synthetic voices. #GnaniAI #GreatIndianAIInternshipChallenge`
3. `One Hindi sentence with five directions, ready in Kannada in under 2 seconds in our saved run. Not streaming; a re-run differs. Built on Gnani Prisma and Timbre. Synthetic voices. #GnaniAI #GreatIndianAIInternshipChallenge`
4. `Customer speaks English, rider speaks Hindi. A few directions only; anything else it refuses out loud. Built on Gnani Prisma and Timbre. Synthetic voices. #GnaniAI #GreatIndianAIInternshipChallenge`
5. `On simulated bike noise the speech engine misheard one word, and the app said so instead of guessing. A single sample on synthetic voices. Built on Gnani Prisma and Timbre. #GnaniAI #GreatIndianAIInternshipChallenge`
