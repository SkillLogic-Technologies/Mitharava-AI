"""Phase 1, Step 1 — prompt tuning harness (no UI).

Runs the two core LLM prompts against hardcoded sample data and prints raw JSON:
  1. Resume parser   (sample resume text -> structured JSON)
  2. Transcript evaluator (sample 8-Q transcript -> scorecard JSON)

Usage:
    python scripts/tune_prompts.py            # runs both
    python scripts/tune_prompts.py resume     # resume parser only
    python scripts/tune_prompts.py eval       # evaluator only

Reads LLM_API_KEY from backend/.env (Gemini key). No other dependencies beyond
what backend/requirements.txt already installs.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("TUNE_MODEL", "gemini-2.0-flash")

# ---------------------------------------------------------------- sample data

SAMPLE_RESUME_TEXT = """
ROHIT VERMA
Email: rohit.verma2003@gmail.com | Phone: +91-9812345678
Jhansi, Uttar Pradesh

EDUCATION
B.Tech Computer Science, Bundelkhand Institute of Engineering & Technology, Jhansi
2021 - 2025 | CGPA: 7.8/10

SKILLS
Python, Java, SQL, HTML/CSS, JavaScript, Flask, MySQL, Git, Data Structures

PROJECTS
1. Hostel Mess Feedback System - Flask web app where students rate daily meals;
   admin dashboard shows weekly trends. Used Flask, MySQL, Chart.js. Deployed on
   PythonAnywhere, used by ~200 students in my hostel.
2. Train Ticket Price Predictor - ML mini-project predicting dynamic ticket prices
   using historical IRCTC data scraped with BeautifulSoup. Linear regression and
   random forest models, 82% accuracy. Python, pandas, scikit-learn.

EXPERIENCE
Web Development Intern, Sparsh Softtech (Jhansi) - Jun 2024 to Aug 2024
- Built and maintained 3 client websites using HTML/CSS/JS and PHP
- Fixed bugs in an inventory management system used by a local distributor

ACHIEVEMENTS
- 2nd place, college hackathon 2024 (team of 4, built the mess feedback app)
- NPTEL certificate: Programming in Java (Elite)
"""

SAMPLE_TRANSCRIPT = [
    {
        "q": "Walk me through your Hostel Mess Feedback System. What problem did it solve and what was your specific contribution?",
        "a": "Sir, in our hostel the mess food quality was inconsistent and students had no way to complain except a paper register nobody read. I built a Flask app where students rate each meal out of 5 and add comments. I made the whole backend and the admin dashboard, my teammate did the frontend styling. The warden actually started using the weekly trend charts to talk to the mess contractor.",
    },
    {
        "q": "You used both linear regression and random forest in your ticket price project. Why two models, and which performed better?",
        "a": "I started with linear regression because it is simple but the accuracy was only around 70% because price depends on things like days before journey in a nonlinear way. Random forest handled that better and gave 82%. So random forest was better.",
    },
    {
        "q": "In your internship you fixed bugs in an inventory system. Describe one bug you fixed and how you found it.",
        "a": "There was a bug where stock count was going negative. I checked the code and found that when two people billed the same item at the same time it subtracted twice without checking. I added a check before update. It was in PHP.",
    },
    {
        "q": "What is the difference between a list and a tuple in Python, and when would you choose one over the other?",
        "a": "List is mutable, tuple is immutable. Tuple is faster and can be used as dictionary key. I use list when data changes, tuple for fixed data like coordinates.",
    },
    {
        "q": "Explain what happens when you type a URL in a browser and press enter.",
        "a": "First DNS lookup happens to get the IP address, then browser makes HTTP request to the server, server sends back HTML, then browser renders it. If there is CSS and JS it downloads those also.",
    },
    {
        "q": "Tell me about a time you had a conflict in a team and how you handled it.",
        "a": "In the hackathon my teammate wanted to use React but we only had 24 hours and nobody knew React well. I said we should use what we know, plain HTML with Bootstrap. He was not happy but I showed him a quick prototype in one hour and he agreed. We came 2nd so it worked out.",
    },
    {
        "q": "Your CGPA is 7.8. Some companies filter at 8.0. How do you respond to that?",
        "a": "Sir honestly in second year I focused more on projects and the internship than exams. My CGPA dropped that year. But I think my practical work shows I can build real things which many high CGPA students cannot.",
    },
    {
        "q": "Where do you see yourself in five years, and why should we hire you for this role?",
        "a": "I want to become a strong backend developer and maybe lead a small team. You should hire me because I learn fast, I have already built things people actually use, and I am ready to work hard.",
    },
]

# ------------------------------------------------------------------- prompts

RESUME_PARSE_PROMPT = """You are a precise resume parser for an Indian campus-placement platform.
Parse the resume text into JSON. Return ONLY valid JSON, no markdown, with EXACTLY this shape:
{
  "name": "",
  "skills": [],
  "projects": [{"title": "", "description": ""}],
  "experience": [{"role": "", "company": "", "duration": ""}],
  "education": "",
  "years_of_experience": 0
}
Rules:
- skills: normalize names (e.g. "HTML/CSS" -> "HTML", "CSS"), no duplicates.
- projects.description: 1-2 sentences capturing what it does, the tech used, and any real-world usage or measurable result.
- years_of_experience: total professional experience in years as a number (internships count as their actual duration, e.g. a 3-month internship = 0.25). For a fresher with one internship this is usually < 1.
- education: single string "degree, institution, year, CGPA if present".
- Do not invent anything not present in the resume."""

EVALUATION_PROMPT = """You are a senior technical interviewer at a top Indian IT services company, evaluating a campus-placement mock interview transcript of a final-year B.Tech student.
Return ONLY valid JSON, no markdown, with EXACTLY this shape:
{
  "overall_score": 0,
  "breakdown": {"technical": 0, "communication": 0, "confidence": 0, "structure": 0},
  "per_question": [{"q": "", "feedback": ""}],
  "top_3_improvements": [],
  "model_answer_example": ""
}
Rules:
- Score each category 1-10 (decimals allowed). overall_score is your holistic judgment, not a plain average.
- Be honest and calibrated: a typical average campus candidate is 5-6, good is 7, exceptional is 8+. Do not inflate.
- per_question: one entry per question, in order. "q" is a short 5-8 word tag of the question. feedback is 1-2 sentences, SPECIFIC to what the candidate actually said - quote or reference their words. Say what was good AND what was missing.
- top_3_improvements: the 3 highest-leverage, actionable changes for the NEXT interview. Not generic advice like "be confident" - tie each to evidence from this transcript.
- model_answer_example: pick the candidate's WEAKEST answer and write a strong model answer to that same question (5-8 sentences), at a level this student could realistically deliver."""

# ------------------------------------------------------------------ plumbing


def parse_json_loose(text: str) -> dict | list | None:
    """Level 1: direct parse. Level 2: substring between first {/[ and last }/]."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def call_llm(system_prompt: str, user_message: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(
        MODEL,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json", "temperature": 0.3},
    )
    return model.generate_content(user_message).text


def run_prompt(label: str, system_prompt: str, user_message: str) -> None:
    print(f"\n{'=' * 70}\n  {label}   (model: {MODEL})\n{'=' * 70}")
    last_raw = ""
    for attempt in (1, 2):
        try:
            last_raw = call_llm(system_prompt, user_message)
        except Exception as e:
            print(f"[attempt {attempt}] LLM call failed: {e}")
            continue
        parsed = parse_json_loose(last_raw)
        if parsed is not None:
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
            return
        print(f"[attempt {attempt}] response was not valid JSON, retrying...")
    print("FAILED after 2 attempts. Last raw response:")
    print(last_raw[:2000])


def main() -> None:
    if not API_KEY:
        sys.exit(
            "LLM_API_KEY is empty in backend/.env - add your Gemini API key "
            "(https://aistudio.google.com/apikey) and rerun."
        )

    which = sys.argv[1] if len(sys.argv) > 1 else "both"

    if which in ("resume", "both"):
        run_prompt("RESUME PARSER", RESUME_PARSE_PROMPT, f"Resume text:\n{SAMPLE_RESUME_TEXT}")

    if which in ("eval", "both"):
        transcript_text = "\n\n".join(
            f"Q{i + 1}: {t['q']}\nCandidate: {t['a']}" for i, t in enumerate(SAMPLE_TRANSCRIPT)
        )
        run_prompt(
            "TRANSCRIPT EVALUATOR",
            EVALUATION_PROMPT,
            f"Interview type: campus placement (IT services), difficulty: medium.\n\nTranscript:\n{transcript_text}",
        )


if __name__ == "__main__":
    main()
