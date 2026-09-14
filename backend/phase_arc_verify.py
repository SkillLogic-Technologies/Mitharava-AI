"""
THROWAWAY verification script — scripted text-mode interview to prove the phase
state machine (OPENING -> BACKGROUND -> CORE w/ follow-ups -> BEHAVIORAL ->
CANDIDATE_Q -> CLOSING) actually works end to end against the LIVE API.

Not wired into the app. Reads BACKEND_URL/credentials only from constants below
(demo account, matches README) — no secrets hardcoded beyond the documented demo
login. Uses the real Gemini call (LLM_API_KEY is configured in backend/.env), not
the mock fallback, so this is a genuine behavioral check.

Usage:
    cd backend
    venv\\Scripts\\activate
    python phase_arc_verify.py
"""
import requests

BASE = "http://localhost:8003/api"
EMAIL = "demo@mitharva.ai"
PASSWORD = "Demo@2026"

# Canned answers a candidate might realistically give at each stage. Written generically
# enough to work regardless of which exact question the model asks at each step, but with
# enough specific, checkable detail (tech choices, a claimed decision) that we can verify
# the model's follow-up actually references something we said.
CANNED_ANSWERS = [
    "Hi, I'm a software developer with about 3 years of experience, mainly working on backend "
    "systems, automation workflows, and more recently some LLM-based tooling.",                     # OPENING
    "I did my B.Tech in Information Technology, then joined DBA Dev Software Solution as a "
    "software developer, where I've been for a few years working on data pipelines and APIs.",       # BACKGROUND 1
    "Before that I did a short training stint in a different domain, but software development is "
    "where I've spent most of my career.",                                                            # BACKGROUND 2
    "One of my main projects was a retrieval-augmented generation pipeline. I chose Langchain for "
    "orchestration specifically because it made it easy to swap vector stores without rewriting "
    "the retrieval logic.",                                                                            # CORE 1
    "The main trade-off was latency - chaining multiple LLM calls added noticeable delay, so I "
    "added caching for repeated queries to bring p95 latency down significantly.",                    # CORE 2 (should get a follow-up referencing Langchain/latency)
    "For the automation workflows, I used Python with a task-queue approach so failures in one "
    "step wouldn't block the rest of the pipeline.",                                                  # CORE 3
    "Once there was a partner API that silently changed its response schema, and our pipeline broke "
    "in production for a few hours before we caught it via a downstream data-quality alert.",        # CORE 4
    "There was a time a teammate and I disagreed on the API contract for a shared service - I set "
    "up a quick doc with both proposals and we picked the one that minimized breaking changes for "
    "existing consumers.",                                                                            # BEHAVIORAL 1
    "A time I failed was underestimating a migration's complexity and missing the first deadline - "
    "I flagged it early to my manager, re-scoped it into phases, and delivered the critical part on "
    "time while the rest followed a week later.",                                                     # BEHAVIORAL 2
    "Yes - could you tell me more about the team structure and what a typical sprint looks like "
    "here?",                                                                                            # CANDIDATE_Q
    "Thank you, this was a great conversation, I appreciate the opportunity.",                          # CLOSING
]


def main():
    s = requests.Session()

    print("Logging in as", EMAIL)
    r = s.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    print("Login OK.\n")

    me = s.get(f"{BASE}/auth/me").json()
    has_resume = bool(me.get("resume_parsed_data") and not me["resume_parsed_data"].get("is_mock"))
    print(f"Account has resume on file: {has_resume} "
          f"(name={me.get('resume_parsed_data', {}).get('name')!r}, "
          f"skills={len(me.get('resume_parsed_data', {}).get('skills') or [])}, "
          f"projects={len(me.get('resume_parsed_data', {}).get('projects') or [])})\n")
    if not has_resume:
        print("WARNING: no resume on this account — CORE-phase resume-grounding cannot be verified. Aborting.")
        return

    print("Creating session: session_type=campus_it, mode=text, difficulty=medium")
    r = s.post(f"{BASE}/sessions", json={
        "session_type": "campus_it",
        "sub_type": "technical",
        "duration_minutes": 30,
        "difficulty": "medium",
        "language": "english",
        "mode": "text",
        "company": "",
    })
    r.raise_for_status()
    session = r.json()
    session_id = session["id"]
    print(f"Session created: {session_id} | current_phase={session.get('current_phase')}\n")

    print("=" * 100)
    print("RUNNING SCRIPTED TURNS")
    print("=" * 100)

    history = []
    opening_question = "Hello! Please introduce yourself."  # question_index 0 has no prior AI question in this harness
    current_question = opening_question
    results = []

    for i, answer in enumerate(CANNED_ANSWERS):
        print(f"\n--- Turn {i} (question_index={i}) ---")
        print(f"[AI asked]      {current_question}")
        print(f"[Candidate says] {answer}")

        r = s.post(f"{BASE}/sessions/turn", json={
            "session_id": session_id,
            "user_message": answer,
            "question_index": i,
            "history": history,
        })
        r.raise_for_status()
        data = r.json()
        parsed = data.get("parsed", {})
        next_q = parsed.get("nextQuestion", "")
        speaker = parsed.get("speakerName", "")
        complete = parsed.get("isInterviewComplete", False)

        # Refresh session to see the stored current_phase
        sess_now = s.get(f"{BASE}/sessions/{session_id}").json()
        phase_now = sess_now.get("current_phase")

        print(f"[Stored phase]  {phase_now}")
        print(f"[AI next]       ({speaker}) {next_q}")
        print(f"[Complete?]     {complete}")

        results.append({
            "turn": i, "phase": phase_now, "speaker": speaker,
            "question": next_q, "prior_answer": answer, "complete": complete,
        })

        history.append({"role": "assistant", "text": current_question})
        history.append({"role": "user", "text": answer})
        current_question = next_q

        if complete:
            print("\n(Interview marked complete by the model — stopping early.)")
            break

    print("\n\n" + "=" * 100)
    print("SUMMARY — QUESTION SEQUENCE WITH PHASES")
    print("=" * 100)
    for r_ in results:
        print(f"turn={r_['turn']:2d} | phase={r_['phase']:16s} | speaker={r_['speaker']:20s} | Q: {r_['question']}")

    phases_seen = [r_["phase"] for r_ in results]
    print("\nPhase order observed:", " -> ".join(dict.fromkeys(phases_seen)))


if __name__ == "__main__":
    main()
