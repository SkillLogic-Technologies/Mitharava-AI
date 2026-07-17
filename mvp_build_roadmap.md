# AI Interview Platform — Full Project Roadmap

From scratch → scaled platform. Built for a 1-2 person team.
Each phase has one goal and an **exit gate** — do not start the next phase until the gate is met.
The golden rule: *ship the smallest thing, put it in front of real users, then expand.*

> Stack note: this repo already runs FastAPI + React + MongoDB. The roadmap's original
> Next.js/Supabase default is superseded — apply each phase's goals to the existing stack.

## Guiding principles

1. **Text before voice.** Voice is the hardest, priciest, buggiest part and is not your edge.
2. **Feedback quality is the product.** The LLM evaluation prompt matters more than any feature.
3. **One wedge first.** Pick a single narrow segment (e.g. Tier-3 engineering colleges in one region) and go deep before widening.
4. **Never ship "unlimited."** Usage-based costs will bleed you. Cap generously instead.
5. **Every phase ends with real users, not a bigger feature list.**

## Phase 0 — Foundation (3-4 days)

Goal: a deployable skeleton and validated demand.

- Working app: auth, DB, deploy. (Already done in this repo.)
- Validate demand in parallel: talk to 10-15 college placement officers (TPOs) about how they run mock interviews today and what hurts most. Try 2 competitors (e.g. Samwaad.ai, Eklavvya) to find where their feedback is weak — that gap is your edge.

**Exit gate:** App deploys, users can sign up, and 3+ TPOs say "yes, we'd pilot this."

## Phase 1 — Text MVP (~2 weeks)  ← CURRENT

Goal: a full text-based mock interview with useful feedback.

Build order — tune the two LLM prompts in a plain script first, before any UI:

1. **Resume parse** (LLM, JSON mode) — PDF → text → structured JSON.
2. **Question generation** (LLM) — parsed resume + interview type + difficulty → 8 personalized questions that reference the candidate's real projects.
3. **Interview chat loop** — simple state machine: show question → user types answer → save → next. No WebSockets, no streaming.
4. **Evaluation + report** (LLM) — full transcript → JSON scorecard (technical, communication, confidence, structure) + per-question feedback + top-3 improvements + a model answer.
5. **Report + history pages** — score bars, transcript, feedback; list of past interviews.

**Exit gate:** A stranger can sign up, upload a resume, complete an interview, and get feedback they find genuinely useful.

## Phase 2 — Pilot & iterate (3-4 weeks)

Goal: prove people actually improve and come back.

- Run a **free pilot with one placement cell** — one batch of ~30 students.
- Watch real usage: where do students drop off? Is the feedback trusted? What breaks?
- Fix the top 5 friction points. Improve prompts based on real transcripts.
- Add basic analytics (signups, interviews completed, drop-off points) — a simple events table is enough.
- Add **one follow-up question per answer** for realism (LLM probes deeper on weak answers).

**Exit gate:** Students voluntarily do a 2nd and 3rd interview, and the TPO says the batch improved. This is the true launch signal.

## Phase 3 — Voice interviews (3-4 weeks)

Goal: real spoken interview experience. Build only after Phase 2's gate.

- STT: Deepgram Nova-3 (lowest latency/cost). TTS: Deepgram Aura or ElevenLabs Flash v2.5.
- Transport: WebSocket for real-time audio; target <2s response.
- Streaming pipeline (mic → STT → LLM → TTS → speaker) with barge-in and graceful fallbacks.
- Cost control from day one: ~₹25-45 per 10-min voice interview. Text stays the free tier; voice is capped per plan.

**Exit gate:** A full voice interview completes end-to-end reliably at a measured, affordable per-interview cost.

## Phase 4 — Advanced AI features (4-6 weeks, pick by demand)

- Adaptive difficulty; multi-interviewer panel (3-5 personas); deeper analytics; (optional, later) video/body-language analysis via MediaPipe.

**Exit gate:** At least one advanced feature is the reason users choose you over alternatives.

## Phase 5 — Niche depth (ongoing)

- Company-specific banks (TCS Ninja vs Digital, Infosys, Wipro, Amazon).
- Current-affairs integration for the govt-job track.
- Hindi + one regional language (text first, then voice).
- Role-specific tracks (SDE, Data Analyst, PM, UPSC personality test).

**Exit gate:** In the chosen niche, content is visibly deeper than any competitor's.

## Phase 6 — B2B & scale (after product-market signal)

- College dashboard for TPOs (batch readiness, weak areas, per-student reports), batch operations, white-label, sales motion.
- Infra hardening: background workers/queue, caching to cut LLM cost, monitoring, load testing.

**Exit gate:** Multiple colleges on paid annual contracts and infra holds under real concurrency.

## Phase 7 — Platform & reach (later)

- Mobile apps; resume optimizer (ATS); LinkedIn review; expert marketplace; adjacent niches (MBA, law, healthcare) — only after dominating the first.

## Cost discipline (from Phase 3 onward)

- Measure cost **per interview** with actual providers before scaling any plan.
- Prompt caching + cheapest acceptable TTS.
- Free tier = text only. Voice is metered/capped. No plan ever says "unlimited."

## The one-line version

Text MVP → pilot with a real college → add voice → add depth (panel, niche content) → sell to colleges → then broaden. Each arrow only happens after real users prove the last step worked.
