# Project: AI Interview Platform (MVP)

Text-first AI mock-interview platform for Indian college campus placements and
government-job aspirants. Built by a 1-2 person team. Ship the smallest useful thing,
then expand. Feedback quality is the product.

## Current phase

Phase 1 — Text MVP. No voice, no payments, no video yet.

## Tech stack (do not change without asking)

- Backend: FastAPI (Python) — single file `backend/server.py`
- Frontend: React 19 (CRA + CRACO) in `frontend/`
- DB: MongoDB (Motor async driver)
- AI: Gemini via `google-generativeai` SDK, JSON-mode structured outputs. Key in `LLM_API_KEY` (backend/.env)
- Do NOT introduce AWS, Kubernetes, microservices, Next.js, Supabase, or a separate backend service.
- Note: `emergentintegrations` imports in server.py are legacy (package unavailable) — replace with direct `google-generativeai` calls, do not add that dependency.

## What the MVP does (scope — build only these)

1. Resume upload (PDF) → parse to structured JSON
2. Generate 8 personalized interview questions from the resume + interview type
3. Text interview: show question → user types answer → save → next
4. Evaluate full transcript → JSON scorecard + feedback report
5. Report page + history of past interviews

## Explicitly OUT of scope right now

Voice (STT/TTS/WebSocket), payments, multi-interviewer panel, video/body-language
analysis, current-affairs scraping, Hindi voice, mobile app. Do not build these unless
explicitly asked.

## Build order (important)

Tune and test the two LLM prompts in a plain script FIRST (`scripts/tune_prompts.py`),
before any UI:
1. Resume parsing prompt
2. Evaluation prompt

Only once those outputs are good, build/improve the UI flow.

## Key LLM prompts (the heart of the product)

- **Resume parse (JSON mode)**: Return ONLY valid JSON with `{name, skills[], projects[{title, description}], experience[{role, company, duration}], education, years_of_experience}`
- **Question generation**: parsed resume + interview type + difficulty → ONLY a JSON array `[{order, text, category}]` of 8 questions (mix of technical, project-based, behavioral). Each question must reference the candidate's actual projects and be specific, not generic.
- **Evaluation**: full transcript → ONLY JSON `{overall_score, breakdown:{technical, communication, confidence, structure}, per_question:[{q, feedback}], top_3_improvements:[], model_answer_example}`. Score each category 1-10. Feedback must be specific and actionable.

## Conventions

- Keep code simple and readable; prefer clarity over cleverness.
- The interview loop is a simple state machine — no WebSockets, no streaming.
- Always validate/parse LLM JSON safely with error handling and a retry on bad JSON.
- Never call an LLM without wrapping in try/except.
- Ask before adding any new dependency or changing the stack.

## Cost rule

No plan is ever "unlimited." Text is the cheap default; anything metered gets a cap.
