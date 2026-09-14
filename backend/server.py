from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
import json
import re
import time
import uuid
import bcrypt
import jwt
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Config
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
# Single LLM provider: Google Gemini (free tier). OpenAI was removed (requires paid credits).
LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-flash-lite-latest')
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY', '')
SARVAM_API_KEY = os.environ.get('SARVAM_API_KEY', '')
RUMIK_API_KEY = os.environ.get('RUMIK_API_KEY', '')
JWT_ALGO = 'HS256'
JWT_EXP_DAYS = 30

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="Mitharva AI API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

logger = logging.getLogger("mitharva")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def _safe_console(text: Optional[str]) -> str:
    """Make arbitrary user text (which may contain Hindi/Devanagari or other non-Latin
    scripts) safe to print()/log on Windows terminals whose console codepage (often cp1252)
    can't encode it - such text would otherwise raise UnicodeEncodeError and crash the
    request. Falls back to \\uXXXX-style escapes for anything the console can't display;
    harmless no-op on UTF-8-capable terminals."""
    if text is None:
        return ""
    try:
        import sys
        encoding = (sys.stdout.encoding or "utf-8")
        return text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
    except Exception:
        return text.encode("ascii", errors="backslashreplace").decode("ascii")


# ============== PROVIDER CIRCUIT BREAKER (TTS + STT) ==============
# Shared by both the /voice/tts (ElevenLabs -> Rumik -> Sarvam) and /voice/stt
# (Sarvam -> Whisper) fallback chains. Problem: a provider that's out of quota/balance
# still costs a full failed round-trip (several hundred ms) on EVERY call, before the
# chain even reaches the funded provider. This breaker remembers "known dead until T"
# per provider and skips straight past it until the cooldown expires, at which point it
# auto-retries once (so a future top-up/refill is picked up automatically — nothing here
# is a permanent "disable this provider").
_CIRCUIT_COOLDOWN_SECONDS = 10 * 60  # 10 minutes
_circuit_breaker_state: Dict[str, float] = {}  # provider_name -> unix timestamp it's unavailable until

# HTTP statuses and message substrings that indicate "this provider is out of quota/funds",
# as opposed to a transient network blip or a bad request — only these should trip the
# breaker, since tripping on a real transient error would wrongly blackout a working,
# funded provider for 10 minutes.
_CIRCUIT_TRIP_STATUSES = {401, 402, 403}
_CIRCUIT_TRIP_SUBSTRINGS = ("quota_exceeded", "insufficient_balance", "insufficient_quota")


def circuit_is_open(provider: str) -> bool:
    """True if this provider is currently marked unavailable (breaker open, calls skipped)."""
    until = _circuit_breaker_state.get(provider)
    return until is not None and time.time() < until


def circuit_record_failure(provider: str, error_text: str) -> bool:
    """Inspect a provider failure and trip the breaker if it looks like a quota/auth/balance
    issue (not a transient error). Returns True if the breaker was tripped."""
    text = (error_text or "")
    status_match = any(f"HTTP {code}" in text for code in _CIRCUIT_TRIP_STATUSES)
    substring_match = any(s in text for s in _CIRCUIT_TRIP_SUBSTRINGS)
    if status_match or substring_match:
        _circuit_breaker_state[provider] = time.time() + _CIRCUIT_COOLDOWN_SECONDS
        return True
    return False


def circuit_record_success(provider: str) -> None:
    """Clear any open breaker for this provider — it's funded/working again."""
    if provider in _circuit_breaker_state:
        del _circuit_breaker_state[provider]


# ============== MODELS ==============
class SignupIn(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = ""
    password: str
    exam_focus: Optional[str] = "upsc"
    state: Optional[str] = ""
    college: Optional[str] = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    state: Optional[str] = None
    college: Optional[str] = None
    bio: Optional[str] = None
    target_year: Optional[int] = None
    preferred_language: Optional[str] = None
    difficulty_preference: Optional[str] = None
    exam_focus: Optional[str] = None
    daf_optional_subject: Optional[str] = None
    daf_home_state: Optional[str] = None
    daf_hobbies: Optional[str] = None
    daf_service_preference: Optional[str] = None
    linkedin: Optional[str] = None


class TtsIn(BaseModel):
    text: str
    language: Optional[str] = "english"
    speaker_name: Optional[str] = None  # legacy/fallback: panel member's name, looked up by exact string match (unreliable - kept only as a last resort)
    speaker_gender: Optional[str] = None  # authoritative: sent by the frontend from the turn response's speakerMember.gender
    speaker_sarvam: Optional[str] = None  # authoritative: speakerMember.sarvam_speaker from the turn response
    speaker_rumik: Optional[str] = None   # authoritative: speakerMember.rumik_speaker from the turn response


class SessionCreate(BaseModel):
    session_type: str
    sub_type: Optional[str] = ""
    duration_minutes: int = 30
    difficulty: str = "medium"
    language: str = "english"
    mode: str = "voice"
    company: Optional[str] = ""


class TurnIn(BaseModel):
    session_id: str
    user_message: str
    question_index: int = 0
    history: Optional[List[Dict[str, Any]]] = None  # prior turns: [{role, text}]


class CompleteSessionIn(BaseModel):
    session_id: str
    transcript: List[Dict[str, Any]]
    duration_seconds: int
    camera_used: bool = False


class PracticeFeedbackIn(BaseModel):
    question: str
    answer: str
    exam_type: str = "upsc"


class NewsQuestionsIn(BaseModel):
    news_title: str
    news_summary: str


class MockPaymentIn(BaseModel):
    plan: str  # 'basic' or 'pro'


# ============== AUTH HELPERS ==============
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXP_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ============== LLM (Google Gemini) ==============
async def call_gemini(system_prompt: str, user_message: str, session_id: str, mock_fn=None) -> str:
    """Call the LLM (Google Gemini, JSON mode). Falls back to mock_fn (defaults to the interview-turn
    mock) if the key is missing or the call fails. Callers with a different response shape (e.g.
    resume parsing) MUST pass their own mock_fn - otherwise the interview-turn mock shape leaks
    into their response."""
    fallback = mock_fn or _mock_interview_response
    if not LLM_API_KEY:
        return fallback(user_message)
    try:
        import google.generativeai as genai
        genai.configure(api_key=LLM_API_KEY)
        model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction=system_prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.3},
        )
        response = await model.generate_content_async(user_message)
        return response.text
    except Exception as e:
        logger.exception("Gemini call failed, using mock: %s", e)
        return fallback(user_message)


def _mock_interview_response(user_message: str) -> str:
    # Deterministic mock fallback used when LLM fails. speakerName here is a placeholder only -
    # session_turn always overwrites it with the actual speaking_member.name resolved from the
    # session's stored roster before this ever reaches the candidate, so no request-time
    # session context is needed here.
    return json.dumps({
        "nextQuestion": "Thank you for that answer. Could you elaborate on a specific example where you demonstrated leadership in a challenging situation?",
        "speakerName": "the interviewer",
        "evaluation": {
            "technicalScore": 7.5,
            "clarityScore": 7.8,
            "structureScore": 7.4,
            "confidenceEstimate": 7.0,
            "overallScore": 7.4,
            "keyStrengths": ["Clear articulation", "Good factual accuracy"],
            "improvementAreas": ["Add more concrete examples"],
            "liveTip": "Try the STAR method: Situation, Task, Action, Result"
        },
        "isInterviewComplete": False
    })


def _resume_block(profile: dict) -> str:
    """Summarize the candidate's parsed resume for the interview system prompt.
    Returns "" if there is no resume - the caller must then instruct the model
    to ask generic questions and NOT use any account identity."""
    parsed = profile.get('resume_parsed_data') or {}
    if not isinstance(parsed, dict) or not parsed or parsed.get('is_mock'):
        return ""
    lines = []
    if parsed.get('skills'):
        lines.append("Skills: " + ", ".join(str(s) for s in parsed['skills'][:15]))
    for p in (parsed.get('projects') or [])[:4]:
        title = p.get('name') or p.get('title') or ''
        desc = (p.get('description') or '')[:200]
        if title:
            lines.append(f"Project: {title} - {desc}")
    for e in (parsed.get('experience') or [])[:3]:
        role = e.get('title') or e.get('role') or ''
        company = e.get('company') or ''
        duration = e.get('duration') or ''
        if role or company:
            lines.append(f"Experience: {role} at {company} ({duration})")
    edu = parsed.get('education')
    if edu:
        if isinstance(edu, list):
            edu = "; ".join(f"{d.get('degree','')} {d.get('institution','')} {d.get('year','')}".strip() for d in edu[:2])
        lines.append(f"Education: {edu}")
    if parsed.get('achievements'):
        lines.append("Achievements: " + "; ".join(str(a) for a in parsed['achievements'][:3]))
    if not lines:
        return ""
    return (
        "\nIMPORTANT - The candidate's RESUME is below. At least HALF of your questions MUST directly reference "
        "these specific items BY NAME (e.g. 'In your Hostel Mess Feedback System project, why did you choose X?'). "
        "Never ask a generic 'tell me about a project' question when you can name their actual project, skill, "
        "internship, or achievement. Probe depth: why they chose the tech, what broke, what they measured.\n"
        "RESUME:\n" + "\n".join(lines) + "\n"
    )


# Common behavioral-question themes get asked with different vocabulary each time
# ("conflict" vs "disagreement" vs "dispute") - canonicalize known synonym clusters to the
# same token before the Jaccard overlap check, or paraphrased repeats of the same behavioral
# theme slip through as "different" questions.
_SYNONYM_CANON = {
    "conflict": "conflicttheme", "disagreement": "conflicttheme", "dispute": "conflicttheme",
    "clash": "conflicttheme", "disagreed": "conflicttheme",
    "failure": "failuretheme", "mistake": "failuretheme", "setback": "failuretheme",
    "failed": "failuretheme", "error": "failuretheme", "wrong": "failuretheme",
    "teamwork": "teamtheme", "collaboration": "teamtheme", "team": "teamtheme",
    "colleague": "peertheme", "teammate": "peertheme", "coworker": "peertheme",
    "pressure": "pressuretheme", "deadline": "pressuretheme", "stress": "pressuretheme",
}


def _normalize_for_similarity(text: str) -> set:
    """Lowercase, strip punctuation, drop common stopwords, canonicalize known behavioral-theme
    synonyms, return a set of significant words for a cheap Jaccard-overlap similarity check
    between two questions."""
    import re
    stopwords = {
        "a", "an", "the", "is", "are", "was", "were", "do", "does", "did", "you", "your",
        "yours", "of", "to", "in", "on", "for", "and", "or", "with", "about", "can", "could",
        "would", "tell", "me", "us", "please", "what", "how", "why", "when", "where", "which",
        "that", "this", "it", "i", "we", "they", "he", "she", "was", "be", "have", "has",
    }
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return {_SYNONYM_CANON.get(w, w) for w in words if w not in stopwords and len(w) > 2}


_THEME_TOKENS = set(_SYNONYM_CANON.values())  # {"conflicttheme", "failuretheme", "teamtheme", "peertheme", "pressuretheme"}


def _is_near_duplicate_question(new_question: str, asked_questions: List[str], threshold: float = 0.45) -> bool:
    """True if new_question is a near-duplicate of any previously-asked question, via two
    checks (either one is enough to flag a repeat):
    1. Jaccard word-overlap >= threshold - catches close paraphrases with similar wording.
    2. Same canonical behavioral-theme token (e.g. both about "conflicttheme") AND sharing at
       least one other significant word - catches theme-level repeats like "conflict with a
       colleague" vs "disagreement with a team member", which use different wording entirely
       but are asking the same behavioral question twice."""
    new_words = _normalize_for_similarity(new_question)
    if not new_words:
        return False
    new_themes = new_words & _THEME_TOKENS
    for prev in asked_questions:
        prev_words = _normalize_for_similarity(prev)
        if not prev_words:
            continue
        overlap = len(new_words & prev_words) / len(new_words | prev_words)
        if overlap >= threshold:
            return True
        shared_themes = new_themes & prev_words
        if shared_themes and len((new_words & prev_words) - _THEME_TOKENS) >= 1:
            return True
    return False


def _extract_asked_questions(history: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Pull out every question the AI has already asked from the turn history (assistant-role
    messages). Used both to inject a hard no-repeat list into the prompt and for the
    similarity post-check."""
    if not history:
        return []
    return [(t.get("text") or "").strip() for t in history if t.get("role") == "assistant" and (t.get("text") or "").strip()]


# Phrases that mean "I didn't hear/understand you, please say the question again" - NOT a
# real answer to the interview question. Matched against a normalized (lowercased, punctuation-
# stripped) copy of the candidate's message. Kept as whole-phrase substrings rather than a
# single giant regex so it's easy to add more variants later; robustness comes from covering
# many short, common phrasings rather than one clever pattern.
_REPEAT_REQUEST_PHRASES = [
    # English - repeat
    "repeat that", "repeat the question", "repeat it", "please repeat", "can you repeat",
    "could you repeat", "say that again", "say it again", "come again", "one more time",
    "pardon", "excuse me", "what was the question", "what did you ask",
    # English - didn't hear / didn't catch
    "didn't hear", "did not hear", "didn't catch", "did not catch", "couldn't hear",
    "could not hear", "i missed that", "i missed the question", "sorry what",
    "sorry, what", "sorry could you", "sorry can you",
    # English - didn't understand / please rephrase (also handled as a repeat, reworded)
    "didn't understand", "did not understand", "don't understand the question",
    "do not understand the question", "can you rephrase", "could you rephrase",
    "please rephrase", "can you simplify", "in simpler words", "explain the question",
    "can you clarify the question", "could you clarify the question",
    # Hindi (Devanagari) - repeat
    "दोहराइए", "दोहरा दीजिए", "दोबारा बताइए", "दोबारा बोलिए", "फिर से बताइए", "फिर से बोलिए",
    "फिर से पूछिए", "एक बार फिर", "दुबारा बताइए", "दुबारा बोलिए",
    # Hindi (Devanagari) - didn't hear / didn't understand
    "सुनाई नहीं दिया", "सुना नहीं", "सुनाई नहीं दी", "समझ नहीं आया", "समझ नहीं आई",
    "समझ में नहीं आया", "क्या पूछा",
    # Romanized Hindi / Hinglish (common typed forms)
    "dobara boliye", "dobara bataiye", "dobara bolo", "phir se boliye", "phir se bataiye",
    "phir se bolo", "dubara boliye", "dubara bataiye", "ek baar phir", "suna nahi",
    "sunai nahi diya", "samajh nahi aaya", "samajh nahi aya", "repeat karo", "repeat kijiye",
]


def detect_repeat_request(user_message: str) -> bool:
    """True if the candidate's message is a request to re-hear/re-explain the question rather
    than an actual answer. Deliberately conservative about length: a long answer that happens
    to contain a short aside like "sorry, one more thing" should NOT be misdetected, so this
    only fires for SHORT messages (a real answer is rarely under ~15 words) that also match one
    of the known phrasings. This keeps it robust without needing an extra LLM call."""
    if not user_message:
        return False
    text = user_message.strip().lower()
    word_count = len(text.split())
    if word_count > 20:
        return False  # too long to plausibly be just a clarification request
    return any(phrase in text for phrase in _REPEAT_REQUEST_PHRASES)


def detect_rephrase_request(user_message: str) -> bool:
    """Subset of detect_repeat_request that specifically asks for the question to be
    reworded/simplified rather than repeated verbatim - still re-asks the SAME question
    (same content), just with an instruction to phrase it more simply."""
    if not user_message:
        return False
    text = user_message.strip().lower()
    rephrase_phrases = [
        "didn't understand", "did not understand", "don't understand the question",
        "do not understand the question", "can you rephrase", "could you rephrase",
        "please rephrase", "can you simplify", "in simpler words", "explain the question",
        "can you clarify the question", "could you clarify the question",
        "समझ नहीं आया", "समझ नहीं आई", "समझ में नहीं आया", "samajh nahi aaya", "samajh nahi aya",
    ]
    word_count = len(text.split())
    if word_count > 20:
        return False
    return any(phrase in text for phrase in rephrase_phrases)


# Matches a first-person self-introduction inside generated question text, e.g. "I am Rajesh
# Menon", "My name is Sneha Kulkarni" - used by the TASK 3 guard below to catch the model
# inventing (or borrowing another panelist's) name instead of using the speaking member's real
# name from the roster.
_SELF_INTRO_PATTERN = re.compile(
    r"\b(?:I am|I'm|My name is)\s+([A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+){0,3})", re.IGNORECASE
)


def check_name_in_text_matches_speaker(question_text: str, speaking_member: dict) -> Optional[str]:
    """If the generated question text contains a first-person self-introduction, check that
    the introduced name matches the speaking member's real name (allowing a partial match,
    e.g. just the first name, since the model may shorten it). Returns the mismatched name
    found in the text if there's a mismatch, or None if it matches / no self-intro was found."""
    if not question_text or not speaking_member.get("name"):
        return None
    m = _SELF_INTRO_PATTERN.search(question_text)
    if not m:
        return None
    said_name = m.group(1).strip()
    expected_name = speaking_member["name"]
    # Loose match: the expected name's significant tokens (skipping honorifics like
    # Shri/Smt/Dr/Adv) should mostly appear in what was said, in either direction.
    honorifics = {"shri", "smt", "dr", "dr.", "adv", "adv.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms."}
    expected_tokens = {t.lower().strip(".") for t in expected_name.split() if t.lower().strip(".") not in honorifics}
    said_tokens = {t.lower().strip(".") for t in said_name.split() if t.lower().strip(".") not in honorifics}
    if expected_tokens & said_tokens:
        return None  # at least one real name token overlaps - treat as a match
    return said_name


def _already_asked_block(asked_questions: List[str]) -> str:
    """Builds the hard no-repeat rule block, listing every question already asked this
    interview so the model can't ask a duplicate or near-duplicate."""
    if not asked_questions:
        return ""
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(asked_questions))
    return (
        "\nQUESTIONS ALREADY ASKED (HARD RULE - NEVER BREAK THIS): You have ALREADY asked the "
        f"candidate the following questions this interview:\n{numbered}\n"
        "Do NOT repeat any of them, word-for-word or paraphrased. Do NOT ask a question that is "
        "semantically similar to one already asked (e.g. 'tell me about a challenge' and 'describe "
        "a difficult situation' count as the same question - never ask both). Every new question "
        "must cover NEW ground the candidate has not already been asked about.\n"
    )


def _resume_coverage_block(profile: dict, asked_questions: List[str]) -> str:
    """Lists the candidate's resume projects/skills split into ALREADY COVERED (mentioned in a
    question already asked) vs NOT YET COVERED, and instructs the model to pick an uncovered
    item for its next CORE-phase question. This stops the CORE phase from asking generic
    'tell me about a project' repeats when the resume has 3-4 concrete projects to pick from."""
    parsed = profile.get('resume_parsed_data') or {}
    if not isinstance(parsed, dict) or not parsed or parsed.get('is_mock'):
        return ""
    items = []
    for p in (parsed.get('projects') or [])[:4]:
        title = p.get('name') or p.get('title') or ''
        if title:
            items.append(title)
    for s in (parsed.get('skills') or [])[:6]:
        if s:
            items.append(str(s))
    if not items:
        return ""
    asked_text = " ".join(asked_questions).lower()
    covered = [item for item in items if item.lower() in asked_text]
    uncovered = [item for item in items if item not in covered]
    if not uncovered:
        return ""  # everything's been touched on - let the model follow up in depth instead
    return (
        "\nRESUME COVERAGE TRACKING: Of the candidate's resume items, these have ALREADY been "
        f"asked about: {', '.join(covered) if covered else '(none yet)'}. These have NOT been "
        f"covered yet: {', '.join(uncovered)}. If you are asking a new (non-follow-up) CORE-phase "
        "question, pick ONE item from the NOT YET COVERED list and ask specifically about its "
        "architecture, a design decision, a trade-off, or a failure - never repeat an already-"
        "covered item unless you are asking a genuine follow-up on the candidate's most recent answer.\n"
    )


def _language_instruction(language: str) -> str:
    if (language or "").lower() == "hindi":
        return (
            "\nLANGUAGE - CRITICAL, NEVER BREAK THIS RULE: Conduct this ENTIRE interview in natural, "
            "conversational Hindi (Devanagari script). Every human-readable text value you write - "
            "nextQuestion, keyStrengths, improvementAreas, liveTip - MUST be in Hindi. Use simple, everyday "
            "spoken Hindi, not overly formal or Sanskritized Hindi. Do NOT switch to English at any point, "
            "even if the candidate answers in English or Hinglish - keep asking your questions in Hindi. "
            "The ONLY things that stay in English are the JSON keys themselves (nextQuestion, speakerName, "
            "evaluation, technicalScore, clarityScore, structureScore, confidenceEstimate, overallScore, "
            "keyStrengths, improvementAreas, liveTip, isInterviewComplete) and speakerName's value (a proper name). "
            "When referring to the candidate's uploaded resume, always call it 'resume' (transliterated as-is, "
            "e.g. 'aapka resume') - do NOT translate it to 'biodata' or 'jeevan vritant'; 'resume' is the correct "
            "word to use even inside Hindi sentences. Match Hindi verb/adjective gender endings to the "
            "candidate's actual gender as evident from their name and resume (e.g. use 'aayi hain', 'chahti hain', "
            "'ki hai' for a female candidate; 'aaye hain', 'chahte hain', 'ki hai' for a male candidate) - never "
            "default to masculine forms for a candidate whose name is clearly feminine.\n"
        )
    return ""


# ============== INTERVIEW PHASE STATE MACHINE ==============
# A real structured panel interview has an arc (warm-up -> background -> deep-dive ->
# behavioral -> candidate questions -> close), not a flat list of unrelated questions.
# Each session_type gets its own ordered phase plan. "weight" is a share of the total
# question budget (INTERVIEW_QUESTION_BUDGET); phases with a fixed "count" instead of a
# weight always take exactly that many questions (e.g. the opening is always 1 question,
# never a fraction of the budget). Remaining budget after fixed-count phases is split
# across weighted phases proportionally. This is plain data, so panels/orderings/shares
# are easy to retune without touching the resolution logic below.
INTERVIEW_QUESTION_BUDGET = 11  # matches the existing "10-12 questions" contract

PHASE_PLANS = {
    "campus_it": [
        {"name": "OPENING", "count": 1, "panel_role": "lead",
         "directive": "Greet the candidate warmly and briefly, then ask them to introduce "
                      "themselves - the classic 'tell me about yourself' opener. Do NOT ask "
                      "anything technical or resume-specific yet."},
        {"name": "BACKGROUND", "count": 2, "panel_role": "lead",
         "directive": "Walk through the candidate's resume/experience at a HIGH LEVEL - their "
                      "overall background, education, and career path so far. Do not go deep "
                      "into technical specifics yet; that comes next."},
        {"name": "CORE", "weight": 0.45, "panel_role": "technical",
         "directive": "Deep-dive into the candidate's ACTUAL resume projects and skills. Ask "
                      "progressively harder questions as this phase continues - start with how "
                      "something works, move to why they made specific technical choices, then "
                      "trade-offs and failure modes. Ground every question in a real project/skill "
                      "already listed in their resume - never invent a project they didn't mention."},
        {"name": "BEHAVIORAL", "weight": 0.20, "panel_role": "hr",
         "directive": "Ask behavioral questions: teamwork, conflict with a colleague, handling "
                      "failure/mistakes, working under pressure. Expect and evaluate STAR-format "
                      "answers (Situation, Task, Action, Result)."},
        {"name": "CANDIDATE_Q", "count": 1, "panel_role": "lead",
         "directive": "Invite the candidate to ask the panel any questions they have about the "
                      "role, team, or company. This is their turn to ask, not yours."},
        {"name": "CLOSING", "count": 1, "panel_role": "lead",
         "directive": "Wrap up warmly: thank the candidate for their time, briefly mention next "
                      "steps (e.g. 'we'll be in touch'), and end the interview."},
    ],
    "upsc": [
        {"name": "OPENING", "count": 1, "panel_role": "lead",
         "directive": "Greet the candidate warmly as the board chairman would, then ask them to "
                      "introduce themselves briefly."},
        {"name": "BACKGROUND", "count": 2, "panel_role": "lead",
         "directive": "Explore the candidate's DAF (Detailed Application Form) at a high level - "
                      "their background, home state, optional subject choice, hobbies - and why "
                      "they chose civil services."},
        {"name": "CURRENT_AFFAIRS", "weight": 0.35, "panel_role": "domain",
         "directive": "Ask about current affairs and their informed opinion on policy matters. "
                      "Probe for reasoning, not just facts - ask them to justify their stance and "
                      "consider counterarguments."},
        {"name": "SITUATIONAL_ETHICS", "weight": 0.30, "panel_role": "hr",
         "directive": "Present administrative/ethical dilemmas relevant to a civil servant's role. "
                      "Evaluate their decision-making process and values, not just the final answer."},
        {"name": "CANDIDATE_Q", "count": 1, "panel_role": "lead",
         "directive": "Invite the candidate to ask the board any questions they have."},
        {"name": "CLOSING", "count": 1, "panel_role": "lead",
         "directive": "Wrap up warmly, thank the candidate, and end the interview."},
    ],
    "banking": [
        {"name": "OPENING", "count": 1, "panel_role": "lead",
         "directive": "Greet the candidate warmly, then ask them to introduce themselves."},
        {"name": "BACKGROUND", "count": 1, "panel_role": "lead",
         "directive": "Ask about their background and specifically WHY they want a career in "
                      "banking - motivation, not technical knowledge yet."},
        {"name": "BANKING_AWARENESS", "weight": 0.40, "panel_role": "technical",
         "directive": "Test banking and financial awareness - monetary policy, banking products, "
                      "regulations, current economic events. Probe for understanding, not rote "
                      "definitions - ask them to explain implications."},
        {"name": "SITUATIONAL", "weight": 0.25, "panel_role": "hr",
         "directive": "Present customer-service and workplace situational scenarios relevant to a "
                      "bank officer's role (e.g. handling an upset customer, a compliance dilemma). "
                      "Evaluate judgment and communication."},
        {"name": "CANDIDATE_Q", "count": 1, "panel_role": "lead",
         "directive": "Invite the candidate to ask the panel any questions they have."},
        {"name": "CLOSING", "count": 1, "panel_role": "lead",
         "directive": "Wrap up warmly, thank the candidate, and end the interview."},
    ],
}
# Every other session_type (ssc, campus_mba, hr, quick, ...) reuses the campus_it plan as a
# reasonable general-purpose structured-interview default rather than falling back to no
# structure at all.
PHASE_PLANS["_default"] = PHASE_PLANS["campus_it"]

# panel_role -> a short human label used in the prompt so the model knows which "panelist"
# is notionally leading this phase. Kept generic (not exam-specific names) since the actual
# on-screen panelist names are assigned per session_type elsewhere in the prompt.
PANEL_ROLE_LABELS = {
    "lead": "the panel chair/lead interviewer",
    "technical": "the technical/domain expert on the panel",
    "hr": "the HR/behavioral panelist",
    "domain": "the subject-matter/current-affairs panelist",
}

# ============== PANEL PERSONA POOLS (randomized roster per session, gender-correct voices) ==============
# Root-cause fix: the LLM's free-text speakerName in its JSON response was never a reliable
# key into a voice map (it paraphrases - "HR Panelist", "Priya Sharma (HR Panelist)" - names
# that never exact-match a roster dict), so voice selection silently fell back to a fixed male
# default every time. The fix: the BACKEND is now the single source of truth for who is
# speaking. At session creation, 3 distinct personas (one per panel_role: lead/technical-or-
# domain/hr) are picked at random from the pools below and stored on the session as
# "panel_roster". Every turn resolves the speaking member from that STORED roster (via the
# phase's panel_role - see resolve_speaking_member), not from anything the LLM says. The LLM
# is still told which persona to voice (so its speakerName/tone stays consistent), but voice
# selection never depends on it being correct.
#
# Each persona carries a gender and BOTH a verified Sarvam bulbul:v3 speaker and a verified
# Rumik mulberry speaker (checked against each provider's live speaker list - do not add a
# name without verifying it against the provider first).
PANEL_PERSONA_POOLS = {
    "upsc": {
        "lead": [
            {"name": "Shri R.K. Sharma", "role": "UPSC Chairman (IAS Retd.)", "gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"},
            {"name": "Smt. Kavita Reddy", "role": "UPSC Chairperson (IAS Retd.)", "gender": "female", "sarvam_speaker": "tanya", "rumik_speaker": "siya"},
            {"name": "Shri Ashok Verma", "role": "UPSC Board Chairman (IFS Retd.)", "gender": "male", "sarvam_speaker": "advait", "rumik_speaker": "theo"},
        ],
        "technical": [
            {"name": "Dr. Priya Nambiar", "role": "Domain Expert", "gender": "female", "sarvam_speaker": "priya", "rumik_speaker": "siya"},
            {"name": "Prof. Ramesh Iyer", "role": "Subject Matter Expert", "gender": "male", "sarvam_speaker": "ashutosh", "rumik_speaker": "noah"},
            {"name": "Dr. Anjali Menon", "role": "Domain Expert", "gender": "female", "sarvam_speaker": "roopa", "rumik_speaker": "mia"},
        ],
        "domain": [
            {"name": "Dr. Priya Nambiar", "role": "Current Affairs Expert", "gender": "female", "sarvam_speaker": "priya", "rumik_speaker": "siya"},
            {"name": "Prof. Ramesh Iyer", "role": "Current Affairs Expert", "gender": "male", "sarvam_speaker": "ashutosh", "rumik_speaker": "noah"},
            {"name": "Dr. Anjali Menon", "role": "Policy Expert", "gender": "female", "sarvam_speaker": "roopa", "rumik_speaker": "mia"},
        ],
        "hr": [
            {"name": "Adv. Mehul Desai", "role": "Legal Expert", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
            {"name": "Smt. Neha Kapoor", "role": "Ethics & Values Panelist", "gender": "female", "sarvam_speaker": "neha", "rumik_speaker": "emma"},
            {"name": "Shri Vivek Rao", "role": "Administrative Expert", "gender": "male", "sarvam_speaker": "aditya", "rumik_speaker": "adam"},
        ],
    },
    "ssc": {
        "lead": [
            {"name": "Shri V.K. Gupta", "role": "SSC Board Chairman", "gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"},
            {"name": "Smt. Sunita Yadav", "role": "SSC Board Chairperson", "gender": "female", "sarvam_speaker": "simran", "rumik_speaker": "sophia"},
        ],
        "technical": [
            {"name": "Shri Prakash Jha", "role": "Administrative Expert", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
            {"name": "Smt. Anita Rao", "role": "Departmental Officer", "gender": "female", "sarvam_speaker": "shreya", "rumik_speaker": "emma"},
        ],
        "hr": [
            {"name": "Smt. Anita Rao", "role": "Departmental Officer", "gender": "female", "sarvam_speaker": "shreya", "rumik_speaker": "emma"},
            {"name": "Shri Prakash Jha", "role": "Administrative Expert", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
        ],
    },
    "banking": {
        "lead": [
            {"name": "Shri S. Krishnan", "role": "Bank GM (Panel Head)", "gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"},
            {"name": "Smt. Meera Iyer", "role": "Bank GM (Panel Head)", "gender": "female", "sarvam_speaker": "neha", "rumik_speaker": "mia"},
        ],
        "technical": [
            {"name": "Smt. Meera Iyer", "role": "Banking Domain Expert", "gender": "female", "sarvam_speaker": "neha", "rumik_speaker": "mia"},
            {"name": "Shri Arun Bhatt", "role": "Banking Domain Expert", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
        ],
        "hr": [
            {"name": "Shri Arun Bhatt", "role": "HR Officer", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
            {"name": "Smt. Pooja Nair", "role": "HR Officer", "gender": "female", "sarvam_speaker": "pooja", "rumik_speaker": "ava"},
        ],
    },
    "campus_it": {
        "lead": [
            {"name": "Rajesh Menon", "role": "Senior Engineering Manager", "gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"},
            {"name": "Sneha Kulkarni", "role": "Senior Engineering Manager", "gender": "female", "sarvam_speaker": "kavya", "rumik_speaker": "ava"},
        ],
        "technical": [
            {"name": "Sneha Kulkarni", "role": "Tech Lead", "gender": "female", "sarvam_speaker": "kavya", "rumik_speaker": "ava"},
            {"name": "Vikram Singh", "role": "Tech Lead", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
        ],
        "hr": [
            {"name": "Vikram Singh", "role": "HR Manager", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
            {"name": "Ishita Sharma", "role": "HR Manager", "gender": "female", "sarvam_speaker": "ishita", "rumik_speaker": "zoya"},
        ],
    },
    "campus_mba": {
        "lead": [
            {"name": "Anand Deshpande", "role": "Senior Partner", "gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"},
            {"name": "Ritu Malhotra", "role": "Senior Partner", "gender": "female", "sarvam_speaker": "ritu", "rumik_speaker": "zoya"},
        ],
        "technical": [
            {"name": "Ritu Malhotra", "role": "Engagement Manager", "gender": "female", "sarvam_speaker": "ritu", "rumik_speaker": "zoya"},
            {"name": "Karan Shah", "role": "Engagement Manager", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
        ],
        "hr": [
            {"name": "Karan Shah", "role": "HR Director", "gender": "male", "sarvam_speaker": "dev", "rumik_speaker": "noah"},
            {"name": "Shreya Kapoor", "role": "HR Director", "gender": "female", "sarvam_speaker": "shreya", "rumik_speaker": "mia"},
        ],
    },
}
PANEL_PERSONA_POOLS["_default"] = PANEL_PERSONA_POOLS["campus_it"]
_PANEL_VOICE_DEFAULT = {"gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"}


def build_random_panel_roster(session_type: str) -> dict:
    """Randomly pick one persona per panel_role (lead/technical/hr, plus domain for upsc) from
    the pools above and return them as a {panel_role: persona} dict to store on the session at
    creation time. Stable for the lifetime of that session; different across sessions.

    DISTINCTNESS: several pools intentionally list the same persona under two roles (e.g.
    campus_it's "Sneha Kulkarni" appears in both "lead" and "technical", so the same tech
    lead can plausibly head the panel OR run the technical round). Picking independently per
    role can therefore select that same name for two different roles in one roster, which
    looks like a bug on screen (two identical panel cards). This draws WITHOUT replacement
    across the whole roster: once a name is used for one role, it's excluded from every other
    role's candidate pool for this session. If a role's pool is fully exhausted (all its
    candidates already used elsewhere), it falls back to the full persona pool for that
    session_type (all roles pooled together) minus already-used names, so a role is only ever
    left without a choice if the entire exam_type's pool is smaller than the roster size -
    which none currently are (min 6 personas per exam_type, panels are max 4 roles)."""
    import random
    pools = PANEL_PERSONA_POOLS.get(session_type, PANEL_PERSONA_POOLS["_default"])
    all_candidates = [c for candidates in pools.values() for c in candidates]

    roster = {}
    used_names = set()
    for role, candidates in pools.items():
        if not candidates:
            continue
        available = [c for c in candidates if c["name"] not in used_names]
        if not available:
            # This role's own pool is exhausted - widen to every persona for this
            # session_type not already used anywhere in the roster.
            available = [c for c in all_candidates if c["name"] not in used_names]
        if not available:
            # Entire exam_type pool exhausted (roster size > distinct personas available) -
            # cannot stay distinct. Log loudly; this should not happen with current pools.
            logger.warning(
                "PANEL ROSTER: ran out of distinct personas for session_type=%s role=%s "
                "(pool size %d < roster size) - reusing a name.",
                session_type, role, len(all_candidates),
            )
            available = candidates
        choice = dict(random.choice(available))
        choice["role"] = choice.get("role") or role  # keep the role-specific title text from the pool entry
        # STABLE ID: this is the single source of truth for "who is this member" everywhere
        # downstream (chat author label, panel card highlight, /voice/tts speaker selection).
        # It's the panel_role key ("lead"/"technical"/"hr"/"domain"), which is unique within
        # one roster and never changes for the lifetime of the session - unlike the persona's
        # display name, which is only meant for showing the candidate, never for matching.
        choice["id"] = role
        roster[role] = choice
        used_names.add(choice["name"])

    # FINAL GUARD: verify no duplicate names slipped through (defensive - the draw-without-
    # replacement logic above should already guarantee this). If somehow still duplicated,
    # rebuild by dropping the later duplicate role down to the widened all_candidates pool.
    seen = set()
    for role, member in list(roster.items()):
        if member["name"] in seen:
            fallback_pool = [c for c in all_candidates if c["name"] not in seen]
            if fallback_pool:
                new_choice = dict(random.choice(fallback_pool))
                new_choice["role"] = new_choice.get("role") or role
                new_choice["id"] = role  # keep the id = panel_role key invariant
                logger.warning(
                    "PANEL ROSTER DUPLICATE CAUGHT BY FINAL GUARD | session_type=%s role=%s "
                    "duplicate_name=%r -> replaced with %r",
                    session_type, role, member["name"], new_choice["name"],
                )
                roster[role] = new_choice
                seen.add(new_choice["name"])
                continue
        seen.add(member["name"])
    return roster


def resolve_speaking_member(sess: dict, phase: dict) -> dict:
    """Authoritative lookup of WHO is speaking this turn: the session's stored panel_roster
    (picked once at session creation - see build_random_panel_roster) indexed BY ID (the
    panel_role key) from the current phase's panel_role. This is the single source of truth
    for the chat author label, the panel card highlight, AND /voice/tts speaker selection -
    never the LLM's free-text speakerName, which doesn't reliably match anything. The returned
    member always carries an "id" field matching a roster key, so all three surfaces can be
    guaranteed to agree (see TASK 2/3 in the consistency fix)."""
    roster = sess.get("panel_roster") or {}
    role = phase.get("panel_role", "lead")
    member = roster.get(role) or roster.get("lead")
    if member:
        # Defensive: guarantee "id" is present and correct even for a roster written by an
        # older code path, or when panel_role didn't exist in the roster and we fell back to
        # "lead" above (the member's own id must reflect which roster slot we actually used).
        member = dict(member)
        member["id"] = role if role in roster else "lead"
        return member
    # Very old sessions created before panel_roster existed have none stored - fall back to a
    # fresh random pick for this session_type rather than a fixed default.
    pools = PANEL_PERSONA_POOLS.get(sess.get("session_type", "upsc"), PANEL_PERSONA_POOLS["_default"])
    candidates = pools.get(role) or pools.get("lead") or []
    if candidates:
        import random
        picked = dict(random.choice(candidates))
        picked["id"] = role
        return picked
    return {"id": "lead", "name": "The Interviewer", **_PANEL_VOICE_DEFAULT}


def resolve_panel_voice_by_gender(gender: Optional[str]) -> dict:
    """Fallback voice-by-gender when a specific member's speaker is somehow missing - NEVER
    falls back to a fixed male speaker for a female member. Used only as a last-resort inside
    resolve_panel_voice below."""
    if (gender or "").lower() == "female":
        return {"gender": "female", "sarvam_speaker": "priya", "rumik_speaker": "siya"}
    return {"gender": "male", "sarvam_speaker": "shubh", "rumik_speaker": "lucas"}


# Live-verified against each provider's actual speaker list (see the batch-test in the
# verification history) - used ONLY to sanity-check that a stored member's sarvam/rumik
# speaker actually matches its own gender field, catching stale/corrupted data (e.g. an old
# session created before a speaker was reassigned to a different gender in the pools).
_SARVAM_FEMALE_SPEAKERS = {"priya", "neha", "pooja", "ritu", "simran", "kavya", "ishita", "shreya", "roopa", "tanya"}
_SARVAM_MALE_SPEAKERS = {"aditya", "ashutosh", "rahul", "rohan", "amit", "dev", "ratan", "varun", "manan", "sumit", "kabir", "aayan", "shubh", "advait", "anand", "tarun"}
_RUMIK_FEMALE_SPEAKERS = {"emma", "mia", "sophia", "ava", "ira", "siya", "aisha", "zoya"}
_RUMIK_MALE_SPEAKERS = {"lucas", "noah", "theo", "adam"}


def resolve_panel_voice(member: Optional[dict]) -> dict:
    """Resolve the TTS voice config from an authoritative member dict (as returned by
    resolve_speaking_member / attached to the turn response) - NOT from a free-text name."""
    if not member:
        return _PANEL_VOICE_DEFAULT
    gender = (member.get("gender") or "male").lower()
    sarvam_speaker = member.get("sarvam_speaker")
    rumik_speaker = member.get("rumik_speaker")
    if not sarvam_speaker or not rumik_speaker:
        by_gender = resolve_panel_voice_by_gender(gender)
        sarvam_speaker = sarvam_speaker or by_gender["sarvam_speaker"]
        rumik_speaker = rumik_speaker or by_gender["rumik_speaker"]

    # SANITY GUARD (TASK 4): a male-gender member must never end up with a female speaker and
    # vice versa. If the stored speaker's known gender contradicts member.gender, the stored
    # data is stale/corrupted - correct it from the verified gender maps and log loudly rather
    # than silently sending a gender-mismatched voice.
    wrong_female_speaker = gender == "male" and sarvam_speaker in _SARVAM_FEMALE_SPEAKERS
    wrong_male_speaker = gender == "female" and sarvam_speaker in _SARVAM_MALE_SPEAKERS
    if wrong_female_speaker or wrong_male_speaker:
        logger.warning(
            "TTS GENDER MISMATCH CORRECTED | member=%r gender=%r had sarvam_speaker=%r (wrong gender) - "
            "correcting to the default %s voice",
            member.get("name"), gender, sarvam_speaker, gender,
        )
        sarvam_speaker = resolve_panel_voice_by_gender(gender)["sarvam_speaker"]
    wrong_female_rumik = gender == "male" and rumik_speaker in _RUMIK_FEMALE_SPEAKERS
    wrong_male_rumik = gender == "female" and rumik_speaker in _RUMIK_MALE_SPEAKERS
    if wrong_female_rumik or wrong_male_rumik:
        logger.warning(
            "TTS GENDER MISMATCH CORRECTED | member=%r gender=%r had rumik_speaker=%r (wrong gender) - "
            "correcting to the default %s voice",
            member.get("name"), gender, rumik_speaker, gender,
        )
        rumik_speaker = resolve_panel_voice_by_gender(gender)["rumik_speaker"]

    return {"gender": gender, "sarvam_speaker": sarvam_speaker, "rumik_speaker": rumik_speaker}


def resolve_voice_from_tts_request(body: "TtsIn") -> dict:
    """Resolve the TTS voice config directly from the request body. Priority order:
    1. AUTHORITATIVE fields (speaker_gender/speaker_sarvam/speaker_rumik) - sent by the
       frontend straight from the turn response's speakerMember, no name-matching involved.
       This is the path that should be used in practice now that session_turn attaches an
       authoritative member to every response.
    2. LEGACY fallback: speaker_name, matched by scanning all persona pools for an exact name
       match (best-effort only - kept so older/cached frontend builds that still only send a
       name don't silently default to a fixed male voice; a random female persona can share a
       name across roles, so this returns the first match found).
    3. Gender-only default if nothing else is available."""
    if body.speaker_sarvam or body.speaker_rumik or body.speaker_gender:
        return resolve_panel_voice({
            "gender": body.speaker_gender,
            "sarvam_speaker": body.speaker_sarvam,
            "rumik_speaker": body.speaker_rumik,
        })
    if body.speaker_name:
        target = body.speaker_name.strip()
        for pools in PANEL_PERSONA_POOLS.values():
            if not isinstance(pools, dict):
                continue
            for candidates in pools.values():
                for candidate in candidates:
                    if candidate["name"] == target:
                        return resolve_panel_voice(candidate)
    return _PANEL_VOICE_DEFAULT


def _resolve_phase_plan(session_type: str) -> list:
    return PHASE_PLANS.get(session_type, PHASE_PLANS["_default"])


def compute_current_phase(session_type: str, question_index: int) -> dict:
    """Given the 0-based question_index (which question we're ABOUT to ask), figure out
    which phase it falls into. Fixed-count phases (OPENING, BACKGROUND, CANDIDATE_Q,
    CLOSING) always take exactly their stated count; the remaining budget is split across
    weighted phases (CORE/BEHAVIORAL/etc.) proportionally to their weight. Returns the
    phase dict plus its resolved 0-based [start, end) question range within the budget."""
    plan = _resolve_phase_plan(session_type)
    fixed_total = sum(p["count"] for p in plan if "count" in p)
    weighted_budget = max(0, INTERVIEW_QUESTION_BUDGET - fixed_total)
    weight_sum = sum(p["weight"] for p in plan if "weight" in p) or 1.0

    cursor = 0
    resolved = []
    for p in plan:
        if "count" in p:
            span = p["count"]
        else:
            span = max(1, round(p["weight"] / weight_sum * weighted_budget))
        resolved.append((p, cursor, cursor + span))
        cursor += span

    # Clamp question_index into the last phase if the model runs slightly over budget
    # (e.g. it asked 12 instead of 11) rather than crashing or returning nothing.
    if question_index >= cursor and resolved:
        phase, start, end = resolved[-1]
        return {**phase, "range_start": start, "range_end": end, "position_in_phase": question_index - start}

    for phase, start, end in resolved:
        if start <= question_index < end:
            return {**phase, "range_start": start, "range_end": end, "position_in_phase": question_index - start}

    # Should be unreachable given the clamp above, but fail safe into the first phase.
    phase, start, end = resolved[0]
    return {**phase, "range_start": start, "range_end": end, "position_in_phase": 0}


def build_phase_prompt_block(session_type: str, question_index: int) -> str:
    """Builds the phase-awareness block injected into the interviewer system prompt:
    which phase we're in, its directive, which panelist leads it, and the follow-up /
    single-question transition rules that make the interview feel structured instead of
    a flat list of disconnected questions."""
    phase = compute_current_phase(session_type, question_index)
    panel_label = PANEL_ROLE_LABELS.get(phase.get("panel_role"), "the interviewer")

    block = (
        f"\nINTERVIEW STRUCTURE - CRITICAL:\n"
        f"You are currently in the **{phase['name']}** phase (question {question_index + 1} of "
        f"~{INTERVIEW_QUESTION_BUDGET}). This phase should be led by {panel_label} - reflect that "
        f"in your speakerName and tone.\n"
        f"Phase goal: {phase['directive']}\n"
        f"TRANSITION RULE: Briefly acknowledge the candidate's previous answer in ONE line, then "
        f"ask exactly ONE question. Never ask multiple questions at once.\n"
    )

    if phase["name"] in ("CORE", "BEHAVIORAL", "CURRENT_AFFAIRS", "SITUATIONAL_ETHICS",
                          "BANKING_AWARENESS", "SITUATIONAL"):
        block += (
            "FOLLOW-UP RULE (HARD REQUIREMENT): Before moving to a new topic, ask ONE probing "
            "follow-up that digs into a specific claim, decision, or trade-off in the candidate's "
            "PREVIOUS answer. Reference something they actually said, by name or detail - do not "
            "ask a generic follow-up. Only move on to a new topic after asking one such follow-up, "
            "or if the candidate has already covered that angle in depth unprompted.\n"
        )
    if phase["name"] == "CORE":
        block += (
            "GROUNDING RULE: Every question in this phase must reference a real project, skill, or "
            "experience item already listed in the candidate's resume above. Do NOT invent a "
            "project, technology, or achievement they did not mention.\n"
        )
    if phase["name"] == "CANDIDATE_Q":
        block += (
            "This is the candidate's turn to ask YOU questions. If they ask something, answer it "
            "briefly and helpfully in nextQuestion, then ask if they have any other questions.\n"
        )
    if phase["name"] == "CLOSING":
        block += (
            "This is the final turn. Thank the candidate, briefly mention next steps, and set "
            "isInterviewComplete to true.\n"
        )
    return block


def build_interview_system_prompt(
    config: dict, profile: dict, question_index: int = 0,
    asked_questions: Optional[List[str]] = None,
    speaking_member: Optional[dict] = None,
) -> str:
    s_type_for_phase = config.get('session_type', 'upsc')
    phase_block = build_phase_prompt_block(s_type_for_phase, question_index)
    asked_questions = asked_questions or []
    speaking_member = speaking_member or {}

    base_rules = f"""Respond ONLY in valid JSON in this EXACT format after every user answer:
{{"nextQuestion":"...","speakerName":"...","evaluation":{{"technicalScore":0,"clarityScore":0,"structureScore":0,"confidenceEstimate":0,"overallScore":0,"keyStrengths":[],"improvementAreas":[],"liveTip":""}},"isInterviewComplete":false}}
Scores are 0-10 decimals. Keep questions concise (1-2 sentences). Set isInterviewComplete: true once you finish the CLOSING phase (around question {INTERVIEW_QUESTION_BUDGET} of ~{INTERVIEW_QUESTION_BUDGET})."""
    resume_data = profile.get('resume_parsed_data') or {}
    has_resume = isinstance(resume_data, dict) and bool(resume_data) and not resume_data.get('is_mock')
    resume_name = (resume_data.get('name') or '').strip() if has_resume else ''

    base_rules = (
        _resume_block(profile) + base_rules + phase_block
        + _already_asked_block(asked_questions) + _resume_coverage_block(profile, asked_questions)
        + _language_instruction(config.get('language'))
    )

    # IDENTITY RULE: the resume is the ONLY source of who the candidate is. The logged-in
    # account's profile.full_name is IRRELEVANT and must never be used - it may belong to a
    # shared/demo account. If no resume was uploaded, address the candidate generically and
    # ask generic (non-resume) questions instead of guessing a name.
    if has_resume and resume_name:
        name = resume_name
        identity_note = (
            f"\nThe candidate's name is '{resume_name}' - this comes ONLY from their uploaded resume. "
            "Use this name and ONLY this name. Ignore any other name you might otherwise associate with "
            "this account; the account login identity is irrelevant and must never be used or mentioned.\n"
        )
    else:
        name = "the candidate"
        identity_note = (
            "\nNo resume has been uploaded for this candidate yet. Do NOT invent or assume any name - "
            "address them generically (e.g. 'you'), or ask their name as your first question if needed. "
            "Do NOT use any account/profile name. Ask general, non-resume-based interview questions for "
            "this category instead. If the candidate asks you to read their resume or asks what their name "
            "is according to their resume, tell them plainly and briefly that no resume has been uploaded "
            "for this session, and ask them to upload one before starting if they want personalized "
            "questions - do NOT talk about 'physical copies' or paper documents, this is a digital app.\n"
        )
    base_rules = identity_note + base_rules
    s_type = config.get('session_type', 'upsc')

    # WHO IS SPEAKING - the persona is now resolved authoritatively by the backend (random
    # per-session roster - see build_random_panel_roster/resolve_speaking_member), not
    # hardcoded to one fixed name. Voice selection reads speaking_member directly and does NOT
    # depend on the LLM echoing this name correctly - but the model was still inventing its
    # OWN name/role inside the actual question text (e.g. "I am Rajesh Menon...") whenever it
    # self-introduced, because the old prompt only told it what to put in the speakerName JSON
    # field, never what name to use for a first-person self-reference inside the question text
    # itself, and never who the OTHER panelists are (so it could accidentally borrow one of
    # their names too). This block fixes both gaps explicitly.
    persona_name = speaking_member.get("name") or "the panel's lead interviewer"
    persona_role = speaking_member.get("role") or "panel member"
    other_members = [
        m for role, m in (config.get("panel_roster") or {}).items()
        if m.get("name") and m.get("name") != persona_name
    ]
    other_members_line = (
        "The OTHER panel members (not you, do not speak as them or introduce yourself as any "
        "of them) are: " + "; ".join(f"{m['name']} ({m.get('role', 'panel member')})" for m in other_members) + ".\n"
        if other_members else ""
    )
    persona_line = (
        f"You are {persona_name}, {persona_role}, a member of this interview panel. When you "
        f"introduce yourself or refer to yourself in first person anywhere in your question "
        f"text (e.g. \"I am ___\", \"My name is ___\"), you MUST use ONLY the name "
        f"'{persona_name}' and the role '{persona_role}'. Do NOT invent any other name for "
        f"yourself, and do NOT use a name you remember from training data or a generic "
        f"placeholder - '{persona_name}' is your ONLY name for this entire interview. "
        f"{other_members_line}"
        f"Use '{persona_name}' as your speakerName in the JSON response too.\n"
    )

    if s_type == 'upsc':
        return f"""{persona_line}This is a UPSC Personality Test board interview.
Candidate: {name}
Optional Subject: {profile.get('daf_optional_subject') or 'Geography'}
Home State: {profile.get('daf_home_state') or 'Uttar Pradesh'}
Hobbies: {profile.get('daf_hobbies') or 'Cricket, Reading'}
This is a structured board interview - follow the INTERVIEW STRUCTURE phase instructions below exactly; do not freelance the ordering.
{base_rules}"""
    if s_type == 'banking':
        return f"""{persona_line}This is a structured IBPS PO interview panel. Candidate: {name}.
Follow the INTERVIEW STRUCTURE phase instructions below exactly; do not freelance the ordering.
{base_rules}"""
    if s_type == 'campus_it':
        return f"""{persona_line}This is a structured technical interview panel at {config.get('company') or 'a top tech company'}. Candidate: {name}.
Follow the INTERVIEW STRUCTURE phase instructions below exactly; do not freelance the ordering.
{base_rules}"""
    if s_type == 'ssc':
        return f"""{persona_line}This is a structured SSC CGL interview board. Candidate: {name}. This is a government service interview - do NOT ask deep software-engineering questions; use the candidate's background only to ask how their skills apply to public service.
Follow the INTERVIEW STRUCTURE phase instructions below exactly; do not freelance the ordering.
{base_rules}"""
    if s_type == 'campus_mba':
        return f"""{persona_line}This is a structured MBA campus interview panel (consulting/finance). Candidate: {name}.
Follow the INTERVIEW STRUCTURE phase instructions below exactly; do not freelance the ordering.
{base_rules}"""
    return f"""{persona_line}This is a structured professional interview panel. Candidate: {name}.
Follow the INTERVIEW STRUCTURE phase instructions below exactly; do not freelance the ordering.
{base_rules}"""


# ============== AUTH ROUTES ==============
@api_router.post("/auth/signup")
async def signup(body: SignupIn):
    existing = await db.users.find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": user_id,
        "full_name": body.full_name,
        "email": body.email,
        "phone": body.phone or "",
        "password": hash_password(body.password),
        "exam_focus": body.exam_focus or "upsc",
        "state": body.state or "",
        "college": body.college or "",
        "preferred_language": "english",
        "difficulty_preference": "medium",
        "plan": "free",
        "interviews_used_this_month": 0,
        "total_interviews": 0,
        "streak_days": 0,
        "bio": "",
        "linkedin": "",
        "target_year": 2026,
        "daf_optional_subject": "",
        "daf_home_state": body.state or "",
        "daf_hobbies": "",
        "daf_service_preference": "IAS",
        "created_at": now,
    }
    await db.users.insert_one(doc)
    token = create_token(user_id)
    user_out = {k: v for k, v in doc.items() if k not in ("password", "_id")}
    return {"token": token, "user": user_out}


@api_router.post("/auth/login")
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"])
    user_out = {k: v for k, v in user.items() if k not in ("password", "_id")}
    return {"token": token, "user": user_out}


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


# ============== PROFILE ROUTES ==============
@api_router.patch("/profile")
async def update_profile(body: ProfileUpdate, user=Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return fresh


# ============== INTERVIEW SESSION ROUTES ==============
@api_router.post("/sessions")
async def create_session(body: SessionCreate, user=Depends(get_current_user)):
    sess_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    # Randomly pick this interview's panel (varied names/genders/voices per session_type),
    # stored once here so it stays stable for the whole interview - see build_random_panel_roster.
    panel_roster = build_random_panel_roster(body.session_type)
    doc = {
        "id": sess_id,
        "user_id": user["id"],
        "session_type": body.session_type,
        "sub_type": body.sub_type or "",
        "duration_minutes": body.duration_minutes,
        "difficulty": body.difficulty,
        "language": body.language,
        "mode": body.mode,
        "company": body.company or "",
        "status": "active",
        "current_phase": "OPENING",
        "panel_roster": panel_roster,
        "transcript": [],
        "overall_score": None,
        "technical_score": None,
        "clarity_score": None,
        "structure_score": None,
        "confidence_score": None,
        "questions_count": 0,
        "camera_used": False,
        "created_at": now,
        "completed_at": None,
    }
    await db.sessions.insert_one(doc)
    print(f"[PANEL DEBUG] session_id={sess_id} session_type={body.session_type} "
          f"panel_roster={ {role: m['name'] + ' (' + m['gender'] + ')' for role, m in panel_roster.items()} }",
          flush=True)
    return {k: v for k, v in doc.items() if k != "_id"}


@api_router.get("/sessions")
async def list_sessions(user=Depends(get_current_user)):
    sessions = await db.sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return sessions


@api_router.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(get_current_user)):
    sess = await db.sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess


@api_router.post("/sessions/turn")
async def session_turn(body: TurnIn, user=Depends(get_current_user)):
    sess = await db.sessions.find_one({"id": body.session_id, "user_id": user["id"]}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.question_index == 0:
        parsed = user.get('resume_parsed_data') or {}
        has_resume = isinstance(parsed, dict) and bool(parsed) and not parsed.get('is_mock')
        identity_used = parsed.get('name') if has_resume and parsed.get('name') else '(no resume - generic identity)'
        logger.info(
            "RESUME DEBUG | session_id=%s account_email=%s account_full_name=%s(IGNORED-not used for identity) "
            "| has_resume=%s resume_name=%s identity_used_by_AI=%s resume_filename=%s resume_uploaded_at=%s "
            "skills_count=%d projects_count=%d language=%s",
            body.session_id, user.get('email'), user.get('full_name'),
            has_resume, parsed.get('name'), identity_used, user.get('resume_filename'), user.get('resume_uploaded_at'),
            len(parsed.get('skills') or []), len(parsed.get('projects') or []), sess.get('language'),
        )
    # Every question the AI has already asked this interview - used both to build the hard
    # no-repeat prompt block and for the similarity post-check below.
    asked_questions = _extract_asked_questions(body.history)

    # REPEAT/REPHRASE REQUEST (TASK 1): if the candidate is asking to hear the question again
    # or have it reworded - NOT actually answering it - re-send the SAME question verbatim (or
    # lightly reworded for a rephrase request). This must happen BEFORE phase resolution/DB
    # update below, so the phase, question_index, and current_phase on the session are all
    # left completely untouched - it's as if this turn never happened except for the reply.
    last_question = asked_questions[-1] if asked_questions else None
    is_repeat = last_question and detect_repeat_request(body.user_message)
    is_rephrase = last_question and not is_repeat and detect_rephrase_request(body.user_message)
    if is_repeat or is_rephrase:
        kind = "rephrase_request" if is_rephrase else "repeat_request"
        # _safe_console() prevents a crash on Windows terminals whose console codepage (e.g.
        # cp1252) can't encode Devanagari/other non-Latin text in a debug print - it degrades
        # to \uXXXX escapes there instead of raising UnicodeEncodeError, while still printing
        # correctly on UTF-8 terminals.
        print(f"[TURN DEBUG] session_id={body.session_id} question_index={body.question_index} "
              f"detected {kind} -> re-asking same question (index unchanged) | "
              f"candidate_said={_safe_console(body.user_message)!r} | last_question={_safe_console(last_question)!r}", flush=True)
        _phase_for_repeat = compute_current_phase(sess.get('session_type', 'upsc'), body.question_index)
        speaking_member_for_repeat = resolve_speaking_member(sess, _phase_for_repeat)
        if is_rephrase:
            # Ask the LLM to reword the SAME question more simply - still not a new topic, no
            # phase/index advance, no scoring. Falls back to the verbatim question if this call
            # fails for any reason (never worse than just repeating it).
            rephrase_prompt = (
                "Reword the following interview question in SIMPLER, more easily understood "
                "language, keeping the exact same meaning and topic - do NOT ask a different "
                "question, do NOT add a new question, just restate this one more simply:\n"
                f"\"{last_question}\"\n"
                "Respond with ONLY the reworded question text, nothing else."
            )
            try:
                reworded_raw = await call_gemini(
                    "You reword interview questions to be simpler. Respond with only the reworded question text.",
                    rephrase_prompt, f"{body.session_id}-rephrase",
                )
                reworded = (reworded_raw or "").strip().strip('"')
                next_q_text = reworded if reworded else last_question
            except Exception:
                next_q_text = last_question
            lead_in = "Sure, let me put that another way: " if (sess.get('language') or '').lower() != 'hindi' else "ठीक है, मैं इसे दूसरे तरीके से पूछता हूँ: "
        else:
            next_q_text = last_question
            lead_in = "Sure, let me repeat that: " if (sess.get('language') or '').lower() != 'hindi' else "ज़रूर, मैं इसे दोबारा कहता हूँ: "
        repeat_parsed = {
            "nextQuestion": f"{lead_in}{next_q_text}",
            "speakerName": speaking_member_for_repeat.get("name"),
            "speakerMember": speaking_member_for_repeat,
            "evaluation": {
                "technicalScore": None, "clarityScore": None, "structureScore": None,
                "confidenceEstimate": None, "overallScore": None,
                "keyStrengths": [], "improvementAreas": [],
                "liveTip": "Take your time - it's completely fine to ask the panel to repeat or clarify a question.",
            },
            "isInterviewComplete": False,
        }
        return {"raw": json.dumps(repeat_parsed, ensure_ascii=False), "parsed": repeat_parsed,
                "panel_roster": sess.get("panel_roster"), "isRepeat": True}

    # Store the resolved phase on the session so it's stable/inspectable (e.g. for a future
    # "you're in the X phase" UI indicator), and log it for verification.
    _phase = compute_current_phase(sess.get('session_type', 'upsc'), body.question_index)

    # AUTHORITATIVE speaking member for this turn, resolved from the session's stored
    # panel_roster (picked once at session creation) + the current phase's panel_role - NOT
    # from anything the LLM says. This is what /voice/tts will use for gender-correct voice
    # selection; the LLM is still told the persona's name so its tone/speakerName stay
    # consistent, but voice selection no longer depends on the LLM getting that string right.
    speaking_member = resolve_speaking_member(sess, _phase)
    system_prompt = build_interview_system_prompt(sess, user, body.question_index, asked_questions, speaking_member)

    print(f"[PHASE DEBUG] session_id={body.session_id} question_index={body.question_index} "
          f"phase={_phase['name']} panel_role={_phase.get('panel_role')} "
          f"position_in_phase={_phase.get('position_in_phase')} range=[{_phase.get('range_start')},{_phase.get('range_end')})",
          flush=True)
    print(f"[TURN DEBUG] session_id={body.session_id} question_index={body.question_index} "
          f"speaking_member_id={speaking_member.get('id')!r} name={speaking_member.get('name')!r} "
          f"role={speaking_member.get('role')!r} speaker={speaking_member.get('sarvam_speaker')!r}",
          flush=True)
    # CONSISTENCY GUARD: the member's name must match what's actually stored in the roster
    # under that same id - this is the single-source-of-truth check requested in TASK 3. If
    # this ever fires, it means resolve_speaking_member returned a member whose identity
    # doesn't match its own id, which would desync the chat label/panel highlight/TTS voice
    # from each other. Should never happen after this fix; kept as a permanent safety net.
    _roster_check = (sess.get("panel_roster") or {}).get(speaking_member.get("id"))
    if _roster_check and _roster_check.get("name") != speaking_member.get("name"):
        logger.warning(
            "PANEL CONSISTENCY MISMATCH | session_id=%s question_index=%s | "
            "speaking_member.id=%r speaking_member.name=%r but roster[id].name=%r - "
            "chat/panel/TTS may disagree on who is speaking!",
            body.session_id, body.question_index, speaking_member.get("id"),
            speaking_member.get("name"), _roster_check.get("name"),
        )
    await db.sessions.update_one({"id": body.session_id}, {"$set": {"current_phase": _phase["name"]}})

    # Include conversation history so the model remembers what the candidate said
    message = body.user_message
    if body.history:
        lines = []
        for t in body.history[-20:]:
            who = "Interviewer" if t.get("role") == "assistant" else "Candidate"
            text = (t.get("text") or "")[:600]
            if text:
                lines.append(f"{who}: {text}")
        if lines:
            message = (
                "Conversation so far:\n" + "\n".join(lines)
                + f"\n\nCandidate's latest answer: {body.user_message}\n"
                "Continue the interview based on everything above. If the candidate corrected any detail (like their name), use the corrected detail."
            )

    raw = await call_gemini(system_prompt, message, body.session_id)
    parsed = _parse_json_loose(raw)

    # REPEAT-QUESTION POST-CHECK: if the generated question is a near-duplicate of one already
    # asked (Jaccard word-overlap check), regenerate ONCE with an explicit "too similar" nudge
    # rather than silently letting the repeat through.
    next_q = parsed.get("nextQuestion") if isinstance(parsed, dict) else None
    if next_q and asked_questions and _is_near_duplicate_question(next_q, asked_questions):
        logger.warning(
            "REPEAT QUESTION DETECTED | session_id=%s question_index=%s | new_question=%r is too similar to a previous question - regenerating once",
            body.session_id, body.question_index, next_q,
        )
        retry_message = (
            message
            + f"\n\nYour previous attempt asked: \"{next_q}\" - that was too similar to a question "
            "already asked in this interview. Ask about something genuinely NEW instead - a "
            "different resume item, or a different angle entirely. Do not just reword the same question."
        )
        raw2 = await call_gemini(system_prompt, retry_message, body.session_id)
        parsed2 = _parse_json_loose(raw2)
        next_q2 = parsed2.get("nextQuestion") if isinstance(parsed2, dict) else None
        if next_q2:
            still_dup = _is_near_duplicate_question(next_q2, asked_questions)
            logger.info(
                "REPEAT QUESTION REGENERATED | session_id=%s | old=%r new=%r still_duplicate=%s",
                body.session_id, next_q, next_q2, still_dup,
            )
            raw, parsed = raw2, parsed2  # use the regenerated version regardless (better than giving up)

    # Override the LLM's free-text speakerName with the authoritative speaking_member's name,
    # and attach the full member (name/gender/role/voice ids) so the frontend can pass it
    # straight to /voice/tts without needing its own hardcoded roster or name-matching.
    if isinstance(parsed, dict):
        parsed["speakerName"] = speaking_member.get("name")
        parsed["speakerMember"] = speaking_member

        # TASK 3 GUARD: catch the model self-introducing under a name that doesn't match the
        # speaking member's real name (e.g. "I am Rajesh Menon..." when the roster's speaking
        # member is actually "Sneha Kulkarni") - this should never fire after the persona_line
        # fix above, but is kept as a permanent regression detector rather than trusting the
        # prompt alone to hold forever.
        question_text = parsed.get("nextQuestion") or ""
        mismatched_name = check_name_in_text_matches_speaker(question_text, speaking_member)
        if mismatched_name:
            print(f"[TURN DEBUG] session_id={body.session_id} question_index={body.question_index} "
                  f"name_in_text mismatch: said={mismatched_name!r} expected={speaking_member.get('name')!r}",
                  flush=True)
            logger.warning(
                "NAME IN TEXT MISMATCH | session_id=%s question_index=%s | question introduced "
                "itself as %r but the speaking member is %r - the LLM invented/borrowed a name.",
                body.session_id, body.question_index, mismatched_name, speaking_member.get("name"),
            )

    return {"raw": raw, "parsed": parsed, "panel_roster": sess.get("panel_roster")}


def _parse_json_loose(text: str) -> dict:
    if not text:
        return {}
    # Try direct
    try:
        return json.loads(text)
    except Exception:
        pass
    # Try to extract JSON block
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    # Malformed-but-structured fallback: the model sometimes emits near-JSON with a stray
    # extra key or a missing quote (e.g. an extra "nextProgram":"" before "nextQuestion", or
    # a dropped opening quote) that breaks strict parsing. Rather than dumping the entire raw
    # blob into nextQuestion (which leaks JSON syntax into what the candidate reads/hears),
    # try to regex out just the nextQuestion string value before falling back further.
    import re
    m = re.search(r'"nextQuestion"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if m:
        try:
            extracted_q = json.loads(f'"{m.group(1)}"')  # unescape \n, \", etc.
        except Exception:
            extracted_q = m.group(1)
        speaker_m = re.search(r'"speakerName"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        # These speakerName placeholders are overwritten by session_turn with the real
        # speaking_member.name from the session's roster before reaching the candidate - see
        # the "Override the LLM's free-text speakerName" block - so a generic placeholder here
        # is fine and never leaks a wrong/hardcoded persona name to the user.
        speaker = speaker_m.group(1) if speaker_m else "the interviewer"
        logger.warning("PARSE FALLBACK: extracted nextQuestion via regex from malformed JSON: %r", text[:300])
        return {"nextQuestion": extracted_q, "speakerName": speaker,
                "evaluation": {"overallScore": 7.0, "technicalScore": 7.0, "clarityScore": 7.0,
                               "structureScore": 7.0, "confidenceEstimate": 7.0,
                               "keyStrengths": [], "improvementAreas": [], "liveTip": ""},
                "isInterviewComplete": False}
    return {"nextQuestion": text.strip(), "speakerName": "the interviewer",
            "evaluation": {"overallScore": 7.0, "technicalScore": 7.0, "clarityScore": 7.0,
                           "structureScore": 7.0, "confidenceEstimate": 7.0,
                           "keyStrengths": [], "improvementAreas": [], "liveTip": ""},
            "isInterviewComplete": False}


@api_router.post("/sessions/complete")
async def complete_session(body: CompleteSessionIn, user=Depends(get_current_user)):
    sess = await db.sessions.find_one({"id": body.session_id, "user_id": user["id"]})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    # Aggregate scores from transcript evaluations
    evals = [t.get("evaluation") for t in body.transcript if t.get("evaluation")]
    def avg(key):
        vals = [float(e.get(key, 0)) for e in evals if e.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else 7.0
    overall = avg("overallScore")
    update = {
        "status": "completed",
        "transcript": body.transcript,
        "duration_seconds": body.duration_seconds,
        "camera_used": body.camera_used,
        "overall_score": overall,
        "technical_score": avg("technicalScore"),
        "clarity_score": avg("clarityScore"),
        "structure_score": avg("structureScore"),
        "confidence_score": avg("confidenceEstimate"),
        "current_affairs_score": round(min(10, overall + 0.2), 2),
        "domain_score": round(min(10, overall + 0.3), 2),
        "questions_count": len([t for t in body.transcript if t.get("role") == "assistant"]),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.sessions.update_one({"id": body.session_id}, {"$set": update})
    # Update user stats
    await db.users.update_one({"id": user["id"]}, {
        "$inc": {"total_interviews": 1, "interviews_used_this_month": 1},
    })
    return {**{k: v for k, v in sess.items() if k != "_id"}, **update}


EVALUATION_PROMPT = """You are a senior interviewer evaluating a full mock-interview transcript of an Indian exam/placement candidate.
Return ONLY valid JSON, no markdown, with EXACTLY this shape:
{"overall_score":0,"breakdown":{"technical":0,"communication":0,"confidence":0,"structure":0},"per_question":[{"q":"","feedback":""}],"top_3_improvements":[],"model_answer_example":""}
Rules:
- Score each category 1-10 (decimals allowed). overall_score is your holistic judgment, not a plain average.
- Be honest and calibrated: a typical average candidate is 5-6, good is 7, exceptional is 8+. Do not inflate.
- per_question: one entry per question, in order. "q" is a short 5-8 word tag of the question. feedback is 1-2 sentences, SPECIFIC to what the candidate actually said. Say what was good AND what was missing.
- top_3_improvements: the 3 highest-leverage, actionable changes for the NEXT interview, each tied to evidence from this transcript.
- model_answer_example: pick the candidate's WEAKEST answer and write a strong model answer to that same question (5-8 sentences) at a level this candidate could realistically deliver."""


def _mock_detailed_report(qa_pairs: list) -> dict:
    return {
        "overall_score": 6.5,
        "breakdown": {"technical": 6.5, "communication": 6.8, "confidence": 6.2, "structure": 6.4},
        "per_question": [
            {"q": (q[:60] + "...") if len(q) > 60 else q,
             "feedback": "Reasonable attempt; add a concrete example and quantify the outcome to strengthen it."}
            for q, _ in qa_pairs
        ],
        "top_3_improvements": [
            "Structure answers with the STAR method (Situation, Task, Action, Result).",
            "Support claims with one specific, quantified example each.",
            "Close answers with a one-line takeaway instead of trailing off.",
        ],
        "model_answer_example": "A strong answer opens with direct context, walks through your specific actions, and ends with a measurable result and what you learned.",
        "is_mock": True,
    }


@api_router.post("/sessions/{session_id}/evaluate")
async def evaluate_session(session_id: str, user=Depends(get_current_user)):
    """Evaluate the full transcript of a completed session into a detailed scorecard report."""
    sess = await db.sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Session is not completed yet")
    if sess.get("detailed_report"):
        return sess["detailed_report"]
    transcript = sess.get("transcript") or []
    # Pair each assistant question with the following user answer
    qa_pairs = []
    pending_q = None
    for t in transcript:
        if t.get("role") == "assistant" and t.get("text"):
            pending_q = t["text"]
        elif t.get("role") == "user" and pending_q:
            qa_pairs.append((pending_q, t.get("text", "")))
            pending_q = None
    if not qa_pairs:
        raise HTTPException(status_code=400, detail="Transcript has no question/answer pairs")
    transcript_text = "\n\n".join(f"Q{i + 1}: {q}\nCandidate: {a}" for i, (q, a) in enumerate(qa_pairs))
    user_msg = f"Interview type: {sess.get('session_type', 'general')}, difficulty: {sess.get('difficulty', 'medium')}.\n\nTranscript:\n{transcript_text[:12000]}"
    report = None
    if LLM_API_KEY:
        for _ in range(2):  # retry once on bad JSON
            raw = await call_gemini(EVALUATION_PROMPT, user_msg, f"evaluate-{session_id}")
            parsed = _parse_json_loose(raw)
            if isinstance(parsed, dict) and "overall_score" in parsed and "breakdown" in parsed:
                report = parsed
                break
    if report is None:
        report = _mock_detailed_report(qa_pairs)
    await db.sessions.update_one({"id": session_id}, {"$set": {"detailed_report": report}})
    return report


# ============== QUESTION BANK ROUTES ==============
@api_router.get("/questions")
async def list_questions(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    type: Optional[str] = None,
):
    q = {}
    if category and category != "all":
        q["category"] = category
    if difficulty and difficulty != "all":
        q["difficulty"] = difficulty
    if type and type != "all":
        q["type"] = type
    items = await db.questions.find(q, {"_id": 0}).to_list(500)
    return items


@api_router.post("/practice/feedback")
async def practice_feedback(body: PracticeFeedbackIn, user=Depends(get_current_user)):
    prompt = f"""You are an expert {body.exam_type} interview coach. Evaluate the candidate's answer.
Return ONLY valid JSON: {{"score": 0-10, "strengths": ["..."], "improvements": ["..."], "modelAnswerApproach": "...", "keyPoints": ["..."]}}"""
    user_msg = f"Question: {body.question}\n\nAnswer: {body.answer}\n\nProvide feedback as JSON."
    raw = await call_gemini(prompt, user_msg, f"practice-{user['id']}-{datetime.now().timestamp()}")
    return _parse_json_loose(raw) or {
        "score": 7.5,
        "strengths": ["Good structure"],
        "improvements": ["Add more concrete examples"],
        "modelAnswerApproach": "Open with a clear thesis, support with 2-3 specific examples, conclude with implications.",
        "keyPoints": ["Use STAR method", "Cite recent examples"],
    }


# ============== CURRENT AFFAIRS ROUTES ==============
@api_router.get("/current-affairs")
async def list_current_affairs(category: Optional[str] = None):
    q = {}
    if category and category != "all":
        q["category"] = category
    items = await db.current_affairs.find(q, {"_id": 0}).sort("published_date", -1).to_list(100)
    return items


@api_router.post("/current-affairs/questions")
async def news_questions(body: NewsQuestionsIn, user=Depends(get_current_user)):
    prompt = """You are a UPSC interview question setter. Given a news item, generate 3 interview questions.
Return ONLY valid JSON array: [{"question": "...", "difficulty": "easy|medium|hard", "hint": "..."}]"""
    user_msg = f"News: {body.news_title}\n\nSummary: {body.news_summary}\n\nGenerate 3 questions."
    raw = await call_gemini(prompt, user_msg, f"news-{user['id']}-{datetime.now().timestamp()}")
    try:
        if not raw:
            raise ValueError("empty")
        start = raw.find('[')
        end = raw.rfind(']')
        return json.loads(raw[start:end + 1]) if start != -1 else []
    except Exception:
        return [
            {"question": f"Discuss the implications of: {body.news_title}", "difficulty": "medium", "hint": "Consider economic, social, political angles"},
            {"question": f"What policy reforms would you propose given: {body.news_title}?", "difficulty": "hard", "hint": "Use multi-stakeholder framework"},
            {"question": f"How does this development impact common citizens?", "difficulty": "easy", "hint": "Ground level perspective"},
        ]


# ============== SUBSCRIPTION ROUTES ==============
@api_router.post("/subscription/mock-pay")
async def mock_pay(body: MockPaymentIn, user=Depends(get_current_user)):
    amounts = {"basic": 199, "pro": 499}
    if body.plan not in amounts:
        raise HTTPException(status_code=400, detail="Invalid plan")
    await db.users.update_one({"id": user["id"]}, {"$set": {"plan": body.plan, "interviews_used_this_month": 0}})
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "amount": amounts[body.plan],
        "plan": body.plan,
        "razorpay_payment_id": f"mock_pay_{uuid.uuid4().hex[:12]}",
        "status": "paid",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.billing_history.insert_one(entry)
    return {"success": True, "plan": body.plan, "amount": amounts[body.plan]}


@api_router.get("/subscription/history")
async def billing_history(user=Depends(get_current_user)):
    items = await db.billing_history.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return items


# ============== DASHBOARD STATS ==============
@api_router.get("/dashboard/stats")
async def dashboard_stats(user=Depends(get_current_user)):
    sessions = await db.sessions.find({"user_id": user["id"], "status": "completed"}, {"_id": 0}).to_list(500)
    total = len(sessions)
    scores = [float(s.get("overall_score") or 0) for s in sessions if s.get("overall_score")]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    last_10 = sorted(sessions, key=lambda x: x.get("created_at") or "")[-10:]
    chart_data = [{
        "date": (s.get("completed_at") or s.get("created_at") or "")[:10],
        "comm": float(s.get("clarity_score") or 0),
        "tech": float(s.get("technical_score") or 0),
    } for s in last_10]
    radar = {
        "Technical": round(sum(float(s.get("technical_score") or 0) for s in sessions) / max(total, 1), 2) or 7.2,
        "Communication": round(sum(float(s.get("clarity_score") or 0) for s in sessions) / max(total, 1), 2) or 7.0,
        "Confidence": round(sum(float(s.get("confidence_score") or 0) for s in sessions) / max(total, 1), 2) or 6.5,
        "Structure": round(sum(float(s.get("structure_score") or 0) for s in sessions) / max(total, 1), 2) or 7.0,
        "CurrentAffairs": round(sum(float(s.get("current_affairs_score") or 0) for s in sessions) / max(total, 1), 2) or 7.0,
        "Domain": round(sum(float(s.get("domain_score") or 0) for s in sessions) / max(total, 1), 2) or 7.5,
    }
    return {
        "total_sessions": total,
        "avg_score": avg_score,
        "streak": user.get("streak_days", 5),
        "percentile": 77,
        "chart_data": chart_data,
        "radar": radar,
        "recent": sessions[-5:][::-1],
    }


# ============== SEED DATA ON STARTUP ==============
SEED_QUESTIONS = [
    # UPSC — 10
    {"category": "upsc", "difficulty": "hard", "type": "situational",
     "question_text": "A powerful local MLA threatens you with transfer if you don't release his relative who was arrested by police in a genuine case. What do you do?"},
    {"category": "upsc", "difficulty": "medium", "type": "current_affairs",
     "question_text": "Explain India's G20 Presidency outcomes and their significance for the Global South."},
    {"category": "upsc", "difficulty": "medium", "type": "long_answer",
     "question_text": "What is cooperative federalism? Cite 3 examples of its success and failure in India."},
    {"category": "upsc", "difficulty": "easy", "type": "long_answer",
     "question_text": "Describe the powers and functions of a District Collector. How has the role evolved post-1991 reforms?"},
    {"category": "upsc", "difficulty": "hard", "type": "situational",
     "question_text": "During election duty you discover evidence of large-scale cash distribution by the ruling party. Your senior officer tells you to ignore it. What do you do?"},
    {"category": "upsc", "difficulty": "medium", "type": "long_answer",
     "question_text": "What is lateral entry into the IAS? Do you support or oppose it? Give reasons."},
    {"category": "upsc", "difficulty": "hard", "type": "situational",
     "question_text": "A natural disaster hits your district. The state government is slow to release funds. NGOs are willing to help but want official permission. How do you handle the next 72 hours?"},
    {"category": "upsc", "difficulty": "easy", "type": "long_answer",
     "question_text": "What is the role of the UPSC in maintaining the integrity of civil services recruitment?"},
    {"category": "upsc", "difficulty": "medium", "type": "current_affairs",
     "question_text": "Comment on the performance of Smart Cities Mission since its launch. What improvements would you suggest?"},
    {"category": "upsc", "difficulty": "hard", "type": "situational",
     "question_text": "You find that a large infrastructure project approved by the state government will displace 5,000 tribal families. The project has political backing. What is your approach as the District Collector?"},
    # Banking — 5
    {"category": "banking", "difficulty": "medium", "type": "long_answer",
     "question_text": "What are Priority Sector Lending norms? What percentage of net bank credit must go to priority sectors?"},
    {"category": "banking", "difficulty": "easy", "type": "long_answer",
     "question_text": "Explain the difference between CRR and SLR. What is their current value?"},
    {"category": "banking", "difficulty": "hard", "type": "current_affairs",
     "question_text": "What is the NARCL (National Asset Reconstruction Company)? How does it address the NPA problem in Indian banks?"},
    {"category": "banking", "difficulty": "medium", "type": "long_answer",
     "question_text": "What is financial inclusion? How have Jan Dhan, Aadhaar, and Mobile (JAM Trinity) contributed to it?"},
    {"category": "banking", "difficulty": "easy", "type": "hr",
     "question_text": "Why do you want to join public sector banking over a private bank or other career options?"},
    # Campus IT — 8
    {"category": "campus_it", "difficulty": "easy", "type": "hr",
     "question_text": "Tell me about a project where you worked in a team. What was your specific contribution and what conflict did you resolve?"},
    {"category": "campus_it", "difficulty": "medium", "type": "long_answer",
     "question_text": "Explain the concept of RESTful APIs. What makes an API truly RESTful? How does it differ from GraphQL?"},
    {"category": "campus_it", "difficulty": "hard", "type": "situational",
     "question_text": "A critical production microservice is failing silently at 3 AM, causing data inconsistencies. You are on-call. Walk me through your incident response, root cause analysis, and prevention steps."},
    {"category": "campus_it", "difficulty": "medium", "type": "hr",
     "question_text": "TCS emphasizes 'Values First.' Describe a situation where you had to choose between taking a shortcut and doing the right thing, even under pressure."},
    {"category": "campus_it", "difficulty": "easy", "type": "hr",
     "question_text": "Where do you see yourself in 5 years? How does joining TCS/Infosys align with your long-term career goals?"},
    {"category": "campus_it", "difficulty": "medium", "type": "long_answer",
     "question_text": "Explain the difference between SQL and NoSQL databases. When would you choose MongoDB over PostgreSQL?"},
    {"category": "campus_it", "difficulty": "hard", "type": "long_answer",
     "question_text": "What is system design? How would you design a URL shortener like bit.ly that handles 100 million requests per day?"},
    {"category": "campus_it", "difficulty": "easy", "type": "hr",
     "question_text": "What is your greatest technical weakness and how are you actively working to improve it?"},
    # SSC — 4
    {"category": "ssc", "difficulty": "medium", "type": "long_answer",
     "question_text": "You have been posted as an Income Tax Inspector in a major commercial city. What are your top 3 priorities in the first month?"},
    {"category": "ssc", "difficulty": "easy", "type": "hr",
     "question_text": "Why do you want to join SSC CGL over pursuing an MBA or private sector career?"},
    {"category": "ssc", "difficulty": "medium", "type": "situational",
     "question_text": "You discover that a senior officer in your department is accepting bribes. How do you handle this?"},
    {"category": "ssc", "difficulty": "easy", "type": "long_answer",
     "question_text": "What are the key functions of a Central Excise Inspector? What is GST and how has it changed indirect taxation?"},
    # Campus MBA — 3
    {"category": "campus_mba", "difficulty": "medium", "type": "hr",
     "question_text": "Walk me through your resume. Why MBA after your engineering degree? Why finance/consulting/marketing?"},
    {"category": "campus_mba", "difficulty": "hard", "type": "situational",
     "question_text": "You are a management trainee and your team is about to miss a key product launch deadline. The project manager is unavailable. What do you do?"},
    {"category": "campus_mba", "difficulty": "easy", "type": "long_answer",
     "question_text": "What is the difference between leadership and management? Give an example of each from your own life."},
]

SEED_CURRENT_AFFAIRS = [
    {"title": "RBI Monetary Policy: Repo Rate Unchanged at 6.25%", "summary": "The Reserve Bank of India MPC voted unanimously to hold the repo rate at 6.25% in May 2026, citing stable inflation at 4.1% and GDP growth forecast of 7.2%.", "source": "RBI", "category": "Economy", "published_date": "2026-05-10"},
    {"title": "Digital India 2.0 Framework Approved", "summary": "Union Cabinet approved the Digital India 2.0 Policy Framework focusing on AI governance, rural broadband expansion through BharatNet Phase 3, and cybersecurity for critical infrastructure.", "source": "PIB", "category": "Polity", "published_date": "2026-05-09"},
    {"title": "India Launches First Indigenous 50-Qubit Quantum Computer", "summary": "IIT Delhi and DRDO jointly unveiled India's first 50-qubit quantum computer under the National Quantum Mission (NQM), making India the 5th nation to achieve this milestone.", "source": "DRDO", "category": "Science & Tech", "published_date": "2026-05-08"},
    {"title": "Kharif MSP 2026-27: 7% Increase Approved", "summary": "CCEA approved MSP increases for all 14 kharif crops. Paddy MSP raised from ₹2,183 to ₹2,336 per quintal. Pulses saw highest increase at 9%.", "source": "Ministry of Agriculture", "category": "Economy", "published_date": "2026-05-07"},
    {"title": "India-Japan 2+2 Dialogue: Defence Partnership Deepened", "summary": "India and Japan signed 3 defence agreements including joint production of underwater surveillance drones and technology transfer for advanced propulsion systems.", "source": "MEA", "category": "International", "published_date": "2026-05-06"},
    {"title": "Supreme Court on Electoral Bonds: Full Transparency Ordered", "summary": "SC directed all political parties to submit complete donor details to Election Commission within 30 days, following up on its landmark 2024 judgment striking down the Electoral Bonds Scheme.", "source": "Supreme Court", "category": "Polity", "published_date": "2026-05-05"},
    {"title": "ISRO's Gaganyaan: Crew Escape Module Test Successful", "summary": "ISRO successfully completed the final Crew Escape System test for the Gaganyaan human spaceflight program, clearing the last major technical hurdle before India's first crewed mission in late 2026.", "source": "ISRO", "category": "Science & Tech", "published_date": "2026-05-04"},
    {"title": "NEP 2020: Four-Year Implementation Report Released", "summary": "Education Ministry report shows 73% of states adopted new curriculum frameworks. 58% of higher education institutions began 4-year undergraduate programs. Teacher training remains the biggest challenge.", "source": "MoE", "category": "Social", "published_date": "2026-05-03"},
    {"title": "India's CAD Narrows to 0.9% of GDP — RBI Data", "summary": "Current Account Deficit narrowed significantly in Q4 FY26 due to services exports reaching a record $42 billion and moderated merchandise import growth. Forex reserves at $680 billion.", "source": "RBI", "category": "Economy", "published_date": "2026-05-02"},
    {"title": "Agni-V MIRV Test: India Joins Elite Club", "summary": "India successfully tested the Agni-V ballistic missile with MIRV (Multiple Independently Targetable Re-entry Vehicle) capability, becoming only the 6th nation to possess this technology.", "source": "DRDO", "category": "Defence", "published_date": "2026-05-01"},
]


async def seed_database():
    # Seed questions if empty
    q_count = await db.questions.count_documents({})
    if q_count == 0:
        for q in SEED_QUESTIONS:
            q["id"] = str(uuid.uuid4())
            q["is_active"] = True
            q["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.questions.insert_many([dict(q) for q in SEED_QUESTIONS])
        logger.info(f"Seeded {len(SEED_QUESTIONS)} questions")
    # Seed current affairs if empty
    ca_count = await db.current_affairs.count_documents({})
    if ca_count == 0:
        for c in SEED_CURRENT_AFFAIRS:
            c["id"] = str(uuid.uuid4())
            c["is_active"] = True
            c["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.current_affairs.insert_many([dict(c) for c in SEED_CURRENT_AFFAIRS])
        logger.info(f"Seeded {len(SEED_CURRENT_AFFAIRS)} current affairs")
    # Seed demo user if not exists
    demo = await db.users.find_one({"email": "demo@mitharva.ai"})
    if not demo:
        demo_id = str(uuid.uuid4())
        demo_doc = {
            "id": demo_id,
            "full_name": "Rahul Kumar",
            "email": "demo@mitharva.ai",
            "phone": "+919876543210",
            "password": hash_password("Demo@2026"),
            "exam_focus": "upsc",
            "state": "Uttar Pradesh",
            "college": "NIT Allahabad",
            "preferred_language": "english",
            "difficulty_preference": "medium",
            "plan": "basic",
            "interviews_used_this_month": 4,
            "total_interviews": 47,
            "streak_days": 5,
            "bio": "UPSC aspirant from Allahabad. Engineering graduate turning to civil services.",
            "linkedin": "linkedin.com/in/rahulkumar",
            "target_year": 2026,
            "daf_optional_subject": "Geography",
            "daf_home_state": "Uttar Pradesh",
            "daf_hobbies": "Cricket, Reading, Social Work",
            "daf_service_preference": "IAS",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(demo_doc)
        # Add demo sessions
        demo_sessions = [
            {"session_type": "upsc", "sub_type": "full_mock", "duration_seconds": 1680, "overall_score": 8.1, "technical_score": 8.5, "clarity_score": 7.8, "structure_score": 8.0, "confidence_score": 6.5, "camera_used": True},
            {"session_type": "campus_it", "sub_type": "tcs_digital", "duration_seconds": 1320, "overall_score": 7.9, "technical_score": 8.0, "clarity_score": 7.5, "structure_score": 7.8, "confidence_score": 7.2, "camera_used": False},
            {"session_type": "banking", "sub_type": "sbi_po", "duration_seconds": 1140, "overall_score": 7.5, "technical_score": 7.2, "clarity_score": 7.8, "structure_score": 7.4, "confidence_score": 6.8, "camera_used": True},
            {"session_type": "upsc", "sub_type": "current_affairs", "duration_seconds": 900, "overall_score": 7.2, "technical_score": 7.5, "clarity_score": 7.0, "structure_score": 7.2, "confidence_score": 6.5, "camera_used": False},
            {"session_type": "ssc", "sub_type": "cgl_panel", "duration_seconds": 1860, "overall_score": 7.0, "technical_score": 7.0, "clarity_score": 7.2, "structure_score": 6.8, "confidence_score": 6.5, "camera_used": False},
            {"session_type": "campus_it", "sub_type": "amazon_sde", "duration_seconds": 1560, "overall_score": 7.8, "technical_score": 8.2, "clarity_score": 7.5, "structure_score": 7.8, "confidence_score": 7.0, "camera_used": True},
            {"session_type": "upsc", "sub_type": "daf_based", "duration_seconds": 1200, "overall_score": 7.4, "technical_score": 7.6, "clarity_score": 7.2, "structure_score": 7.5, "confidence_score": 6.2, "camera_used": True},
            {"session_type": "banking", "sub_type": "rbi_grade_b", "duration_seconds": 1080, "overall_score": 6.8, "technical_score": 7.0, "clarity_score": 6.5, "structure_score": 6.8, "confidence_score": 6.0, "camera_used": False},
            {"session_type": "campus_it", "sub_type": "infosys", "duration_seconds": 1440, "overall_score": 7.6, "technical_score": 7.8, "clarity_score": 7.4, "structure_score": 7.6, "confidence_score": 6.8, "camera_used": False},
            {"session_type": "upsc", "sub_type": "full_mock", "duration_seconds": 1740, "overall_score": 6.5, "technical_score": 6.8, "clarity_score": 6.2, "structure_score": 6.5, "confidence_score": 5.8, "camera_used": False},
            {"session_type": "ssc", "sub_type": "chsl", "duration_seconds": 960, "overall_score": 6.9, "technical_score": 7.0, "clarity_score": 7.0, "structure_score": 6.8, "confidence_score": 6.5, "camera_used": False},
            {"session_type": "campus_mba", "sub_type": "hr_round", "duration_seconds": 1320, "overall_score": 7.3, "technical_score": 7.2, "clarity_score": 7.5, "structure_score": 7.2, "confidence_score": 7.0, "camera_used": False},
        ]
        base_date = datetime.now(timezone.utc) - timedelta(days=45)
        for i, s in enumerate(demo_sessions):
            created = (base_date + timedelta(days=i * 3)).isoformat()
            s.update({
                "id": str(uuid.uuid4()),
                "user_id": demo_id,
                "difficulty": "medium",
                "language": "english",
                "mode": "voice" if s["camera_used"] else "voice",
                "status": "completed",
                "current_affairs_score": round(s["overall_score"] - 0.2, 2),
                "domain_score": round(s["overall_score"] + 0.3, 2),
                "questions_count": 12,
                "transcript": [],
                "created_at": created,
                "completed_at": created,
            })
        await db.sessions.insert_many(demo_sessions)
        logger.info("Seeded demo user with 12 sessions")


@app.on_event("startup")
async def on_startup():
    try:
        await seed_database()
    except Exception as e:
        logger.exception("Seed failed: %s", e)


# ============== VOICE STT (Sarvam Saarika primary; OpenAI Whisper secondary if configured) ==============
# The frontend also has a browser SpeechRecognition mode that never calls this endpoint at all,
# so voice input never fully breaks even if both providers below are unavailable.
_OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '')
_STT_LANG_MAP = {"english": "en-IN", "hindi": "hi-IN", "hinglish": "hi-IN", "tamil": "ta-IN", "bengali": "bn-IN", "marathi": "mr-IN"}
_SARVAM_AUTO_DETECT_LANG_CODE = "unknown"  # per Sarvam docs: "Use when the language is not known"


async def _resolve_stt_language_code(session_id: Optional[str], language_param: Optional[str], user_id: str) -> tuple:
    """Resolve the Sarvam language_code to use, in priority order:
      1. The SESSION's stored `language` field (most reliable — doesn't depend on the
         frontend's multipart binding, and reflects what the interview actually is,
         e.g. a Hindi UPSC session), if session_id was provided and the session is found.
      2. The `language` request param, if the session lookup didn't yield a value.
      3. Sarvam auto-detect ('unknown') as the last resort — NEVER silently default to
         English, since that would misrecognize Hindi speech as empty/garbage.
    Returns (lang_code, source_label) for logging."""
    if session_id:
        try:
            sess = await db.sessions.find_one({"id": session_id, "user_id": user_id}, {"_id": 0, "language": 1})
            if sess and sess.get("language"):
                mapped = _STT_LANG_MAP.get(sess["language"].lower())
                if mapped:
                    return mapped, f"session.language={sess['language']!r}"
        except Exception as e:
            print(f"[STT DEBUG] session language lookup failed (non-fatal): {e}", flush=True)

    if language_param:
        mapped = _STT_LANG_MAP.get(language_param.lower())
        if mapped:
            return mapped, f"request_param language={language_param!r}"

    return _SARVAM_AUTO_DETECT_LANG_CODE, "no session/param language available — Sarvam auto-detect"


async def _sarvam_stt_text(contents: bytes, filename: str, lang_code: str) -> str:
    """Call Sarvam Saarika STT. Returns transcript text. Raises on failure.
    `lang_code` must already be a resolved Sarvam language_code (e.g. 'hi-IN', 'en-IN',
    'unknown') — resolution happens once per request in voice_stt(), not per-clip, so
    every segment of a chunked long answer uses the same language."""
    import aiohttp, mimetypes
    filename = filename or "audio.webm"
    content_type = mimetypes.guess_type(filename)[0] or "audio/webm"
    url = "https://api.sarvam.ai/speech-to-text"
    form = aiohttp.FormData()
    form.add_field("model", "saarika:v2.5")
    form.add_field("language_code", lang_code)
    form.add_field("file", contents, filename=filename, content_type=content_type)
    async with aiohttp.ClientSession() as http:
        # 120s (not 30s) — a slow transcription must not time out mid-request. This is
        # independent of Sarvam's own ~30s max-audio-per-call limit, which is handled by
        # chunking in voice_stt() before this function is ever called with long audio.
        async with http.post(url, data=form, headers={"api-subscription-key": SARVAM_API_KEY},
                              timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                err_text = (await resp.text())[:300]
                raise RuntimeError(f"Sarvam STT HTTP {resp.status}: {err_text}")
            data = await resp.json()
    return (data.get("transcript") or "").strip()


def _probe_audio_duration_seconds(contents: bytes) -> Optional[float]:
    """Shells out to ffprobe to get exact audio duration for any container (webm/opus, mp4,
    wav). Returns None if ffprobe is unavailable or parsing fails; never raises, since a
    probe failure must not affect the real STT request (falls back to the single-call path)."""
    import subprocess, tempfile
    try:
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", tmp_path],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        print(f"[STT DEBUG] duration probe failed (non-fatal): {e}", flush=True)
        return None


_STT_CHUNK_THRESHOLD_S = 28  # above this, split into segments before calling Sarvam
_STT_SEGMENT_TIME_S = 25     # ffmpeg -segment_time — stays safely under Sarvam's ~30s cap


def _split_audio_into_segments(contents: bytes, filename: str) -> Optional[list]:
    """Uses ffmpeg to split long audio into ~_STT_SEGMENT_TIME_S-second WAV segments
    (16kHz mono, re-encoded for reliability regardless of the source container/codec).
    Returns a sorted list of segment file paths, or None if ffmpeg fails for any reason
    (caller falls back to the single-call path — this must never crash the request).
    Caller is responsible for deleting the returned files AND the temp directory."""
    import subprocess, tempfile, glob
    try:
        work_dir = tempfile.mkdtemp(prefix="stt_chunks_")
        suffix = os.path.splitext(filename or "audio.webm")[1] or ".webm"
        input_path = os.path.join(work_dir, f"input{suffix}")
        with open(input_path, "wb") as f:
            f.write(contents)

        output_pattern = os.path.join(work_dir, "seg_%03d.wav")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1",
             "-f", "segment", "-segment_time", str(_STT_SEGMENT_TIME_S), output_pattern],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"[STT DEBUG] ffmpeg split FAILED (rc={result.returncode}): {result.stderr[-500:]}", flush=True)
            return None

        segments = sorted(glob.glob(os.path.join(work_dir, "seg_*.wav")))
        if not segments:
            print("[STT DEBUG] ffmpeg split produced no segments", flush=True)
            return None
        return segments
    except Exception as e:
        print(f"[STT DEBUG] ffmpeg split raised (non-fatal): {e}", flush=True)
        return None


async def _transcribe_one_clip(contents: bytes, filename: str, language: Optional[str], sarvam_lang_code: str, duration_label) -> str:
    """Transcribe a single clip (either the whole recording, or one chunk of it) via
    Sarvam Saarika first, then OpenAI Whisper if configured. Raises if both fail — caller
    decides how to handle that (top-level 500 for the single-call path, or 'skip this
    segment, keep the others' for the chunked path).

    `sarvam_lang_code` is the already-resolved Sarvam language_code (see
    _resolve_stt_language_code) — resolved ONCE per request from the session, not
    re-derived per clip. `language` (the raw "hindi"/"english" string) is kept separately
    for the Whisper fallback, which uses its own 2-letter ISO codes."""
    if SARVAM_API_KEY and not circuit_is_open("sarvam_stt"):
        try:
            text = await _sarvam_stt_text(contents, filename, sarvam_lang_code)
            circuit_record_success("sarvam_stt")
            print(f"[STT DEBUG] PROVIDER USED: Sarvam Saarika (success) | lang_code={sarvam_lang_code} | duration={duration_label} | transcript_len={len(text)}", flush=True)
            return text
        except Exception as e:
            tripped = circuit_record_failure("sarvam_stt", str(e))
            print(f"[STT DEBUG] Sarvam STT FAILED | lang_code={sarvam_lang_code} | duration={duration_label} | exact_error={e}"
                  + (" | CIRCUIT TRIPPED (skipping for 10min)" if tripped else ""), flush=True)
            logger.warning("Sarvam STT failed, trying Whisper: %s", e)
    elif SARVAM_API_KEY:
        print(f"[STT DEBUG] Sarvam SKIPPED (circuit open) | duration={duration_label}", flush=True)

    if _OPENAI_KEY and not circuit_is_open("whisper_stt"):
        try:
            from openai import AsyncOpenAI
            client_ai = AsyncOpenAI(api_key=_OPENAI_KEY)
            bio = io.BytesIO(contents)
            bio.name = filename or "audio.webm"
            kwargs = {"file": bio, "model": "whisper-1", "response_format": "json"}
            if language and language != "auto":
                lang_map = {"english": "en", "hindi": "hi", "hinglish": "hi", "tamil": "ta", "bengali": "bn", "marathi": "mr"}
                kwargs["language"] = lang_map.get(language, language[:2])
            response = await client_ai.audio.transcriptions.create(**kwargs)
            text = getattr(response, "text", str(response))
            circuit_record_success("whisper_stt")
            print(f"[STT DEBUG] PROVIDER USED: OpenAI Whisper (success) | duration={duration_label}", flush=True)
            return text
        except Exception as e:
            tripped = circuit_record_failure("whisper_stt", str(e))
            print(f"[STT DEBUG] Whisper STT FAILED | duration={duration_label} | exact_error={e}"
                  + (" | CIRCUIT TRIPPED (skipping for 10min)" if tripped else ""), flush=True)
            logger.warning("Whisper STT failed: %s", e)
    elif _OPENAI_KEY:
        print(f"[STT DEBUG] Whisper SKIPPED (circuit open) | duration={duration_label}", flush=True)
    else:
        print(f"[STT DEBUG] Whisper SKIPPED: no OPENAI_API_KEY in .env | duration={duration_label}", flush=True)

    raise RuntimeError("No STT provider available for this clip")


@api_router.post("/voice/stt")
async def voice_stt(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    """Transcribe audio to text. Tries Sarvam Saarika first (best for Hindi/Indian languages),
    then OpenAI Whisper if configured. Returns { text }.

    Sarvam's STT has a hard ~30s max audio length per call. Recordings longer than
    _STT_CHUNK_THRESHOLD_S are split via ffmpeg into ~_STT_SEGMENT_TIME_S-second WAV
    segments first, each transcribed independently, then joined — so long interview
    answers no longer fail outright.

    LANGUAGE RESOLUTION: `language` was previously declared without Form(...), so it was
    bound as a query param while the frontend sends it as a multipart form field — it was
    ALWAYS None regardless of the interview's actual language (English happened to "work"
    only because Sarvam's fallback default was en-IN; Hindi silently broke). Fixed by (a)
    declaring `language` as Form(...) so the field actually binds, and (b) preferring the
    SESSION's stored language (via the now also-sent `session_id`) as the primary source of
    truth, since it doesn't depend on any per-request binding working correctly at all."""
    contents = await file.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25MB)")

    sarvam_lang_code, lang_source = await _resolve_stt_language_code(session_id, language, user["id"])

    # DIAGNOSTIC (temporary) — exact size + duration reaching STT, before any provider call.
    _duration = _probe_audio_duration_seconds(contents)
    print(f"[STT DEBUG] uploaded file={file.filename!r} size_bytes={len(contents)} "
          f"duration_seconds={_duration if _duration is not None else 'UNKNOWN (ffprobe unavailable)'} "
          f"language_param={language!r} session_id={session_id!r} "
          f"resolved_lang_code={sarvam_lang_code!r} (source: {lang_source})", flush=True)

    # --- Short clip (or unknown duration — ffprobe unavailable): single-call path, unchanged. ---
    if _duration is None or _duration <= _STT_CHUNK_THRESHOLD_S:
        try:
            text = await _transcribe_one_clip(contents, file.filename, language, sarvam_lang_code, _duration)
            return {"text": text}
        except Exception as e:
            print(f"[STT DEBUG] ALL PROVIDERS EXHAUSTED | duration_seconds={_duration} — frontend will show 'unable to hear'", flush=True)
            raise HTTPException(status_code=500, detail="No STT provider available; use Browser STT instead")

    # --- Long clip: split into segments and transcribe each, then join. ---
    print(f"[STT DEBUG] duration {_duration:.1f}s > {_STT_CHUNK_THRESHOLD_S}s threshold — splitting into "
          f"~{_STT_SEGMENT_TIME_S}s segments before transcription", flush=True)
    segments = _split_audio_into_segments(contents, file.filename)

    if not segments:
        # ffmpeg unavailable/failed — fall back to the single call. It may still fail on
        # Sarvam's own duration limit, but this is strictly no worse than before the fix.
        print("[STT DEBUG] chunking unavailable — falling back to single-call path for long clip", flush=True)
        try:
            text = await _transcribe_one_clip(contents, file.filename, language, sarvam_lang_code, _duration)
            return {"text": text}
        except Exception:
            print(f"[STT DEBUG] ALL PROVIDERS EXHAUSTED | duration_seconds={_duration} — frontend will show 'unable to hear'", flush=True)
            raise HTTPException(status_code=500, detail="No STT provider available; use Browser STT instead")

    try:
        print(f"[STT DEBUG] split into {len(segments)} segment(s): {[os.path.basename(s) for s in segments]}", flush=True)
        transcripts = []
        succeeded = 0
        for i, seg_path in enumerate(segments):
            try:
                with open(seg_path, "rb") as f:
                    seg_bytes = f.read()
                seg_duration = _probe_audio_duration_seconds(seg_bytes)
                seg_text = await _transcribe_one_clip(seg_bytes, os.path.basename(seg_path), language, sarvam_lang_code, seg_duration)
                # Provider call succeeded even if the segment was silence/noise and came back
                # empty — that's a real, valid result, not a failure. Only an exception (raised
                # by _transcribe_one_clip when every provider errors out) counts as failed.
                succeeded += 1
                print(f"[STT DEBUG] segment {i+1}/{len(segments)} OK | duration={seg_duration} | text={seg_text[:80]!r}", flush=True)
                if seg_text:
                    transcripts.append(seg_text)
            except Exception as e:
                # Partial failure — log and continue with the remaining segments rather than
                # failing the whole answer.
                print(f"[STT DEBUG] segment {i+1}/{len(segments)} FAILED (skipping, continuing): {e}", flush=True)

        if succeeded == 0:
            print(f"[STT DEBUG] ALL SEGMENTS FAILED | duration_seconds={_duration} — frontend will show 'unable to hear'", flush=True)
            raise HTTPException(status_code=500, detail="No STT provider available; use Browser STT instead")

        combined = " ".join(transcripts).strip()
        print(f"[STT DEBUG] PROVIDER USED: Sarvam/Whisper chunked ({succeeded}/{len(segments)} segments succeeded, "
              f"{len(transcripts)} had non-empty text) | combined_transcript_len={len(combined)}", flush=True)
        return {"text": combined}
    finally:
        # Clean up every segment file and the temp directory they live in.
        work_dir = os.path.dirname(segments[0]) if segments else None
        for seg_path in segments:
            try:
                os.unlink(seg_path)
            except Exception:
                pass
        if work_dir:
            try:
                os.rmdir(work_dir)
            except Exception:
                pass


# ============== VOICE TTS (Rumik Silk primary, ElevenLabs + Sarvam fallback) ==============
# Rumik Silk (mulberry model) gave the best result in testing: correctly pronounces English
# proper nouns (resume project/tech names) AND handles Hindi/Hinglish naturally. ElevenLabs
# has a small free-tier quota and no Indian accent on the free tier. Sarvam is on bulbul:v3
# now (v2 mispronounced English proper nouns/tech terms — see A/B test in tts_ab_test.py);
# v2 and v3 do NOT share speaker names, so SARVAM_TTS_SPEAKER must be a valid v3 speaker.
# ElevenLabs and Sarvam remain as fallbacks so voice never drops to the robotic browser
# speechSynthesis just because one provider's quota/limit is hit.
RUMIK_SPEAKER = os.environ.get('RUMIK_SPEAKER', 'lucas')  # confirmed-male voice (deep pitch); "siya" is a female alternative
ELEVENLABS_VOICE_ID = os.environ.get('ELEVENLABS_VOICE_ID', 'pNInz6obpgDQGcFmaJgB')  # "Adam" - default multilingual voice
SARVAM_TTS_SPEAKER = os.environ.get('SARVAM_TTS_SPEAKER', 'shubh')  # bulbul:v3 voice — v2 used 'hitesh', which does NOT exist on v3 (HTTP 400)


async def _rumik_tts_audio(text: str, voice_config: dict) -> bytes:
    """Call Rumik Silk (mulberry) TTS. Returns raw WAV bytes. Raises on failure."""
    import aiohttp
    url = "https://silk-api.rumik.ai/v1/tts"
    headers = {"Authorization": f"Bearer {RUMIK_API_KEY}", "Content-Type": "application/json; charset=utf-8"}
    gender = voice_config.get("gender", "male")
    description = (
        f"a deep male indian voice in his 30s, warm professional tone, conversational interviewer pacing"
        if gender == "male" else
        f"a warm female indian voice in her 30s, professional tone, conversational interviewer pacing"
    )
    payload = {
        "model": "mulberry",
        "text": text[:2000],
        "description": description,
        "speaker": voice_config.get("rumik_speaker", RUMIK_SPEAKER),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with aiohttp.ClientSession() as http:
        async with http.post(url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                err_text = (await resp.text())[:300]
                raise RuntimeError(f"Rumik TTS HTTP {resp.status}: {err_text}")
            return await resp.read()


async def _elevenlabs_tts_audio(text: str) -> bytes:
    """Call ElevenLabs TTS. Returns raw MP3 bytes. Raises on failure.
    NOTE: still a single fixed voice (ELEVENLABS_VOICE_ID) - ElevenLabs is not gender-mapped
    per panel member yet, since its free-tier quota is usually exhausted anyway (see Rumik/
    Sarvam below, which ARE gender-matched and serve as the practical primary path)."""
    import aiohttp
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    payload = {
        "text": text[:2000],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                err_text = (await resp.text())[:300]
                raise RuntimeError(f"ElevenLabs TTS HTTP {resp.status}: {err_text}")
            return await resp.read()


async def _sarvam_tts_audio(text: str, language: str, voice_config: dict) -> bytes:
    """Call Sarvam Bulbul TTS. Returns raw WAV bytes. Raises on failure."""
    import aiohttp, base64
    lang_code = "hi-IN" if (language or "").lower() == "hindi" else "en-IN"
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {"Content-Type": "application/json; charset=utf-8", "api-subscription-key": SARVAM_API_KEY}
    payload = {
        "inputs": [text[:1500]],
        "target_language_code": lang_code,
        "speaker": voice_config.get("sarvam_speaker", SARVAM_TTS_SPEAKER),
        "model": "bulbul:v3",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with aiohttp.ClientSession() as http:
        async with http.post(url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                err_text = (await resp.text())[:300]
                raise RuntimeError(f"Sarvam TTS HTTP {resp.status}: {err_text}")
            data = await resp.json()
    return base64.b64decode(data["audios"][0])


@api_router.post("/voice/tts")
async def voice_tts(body: TtsIn, user=Depends(get_current_user)):
    """Synthesize speech for the interviewer's line. Tries ElevenLabs first (most natural voice
    quality), then Rumik Silk, then Sarvam Bulbul. If all fail/unconfigured, returns a clean
    error so the frontend can fall back to the browser's built-in speechSynthesis as a last
    resort."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    voice_config = resolve_voice_from_tts_request(body)
    # DIAGNOSTIC (temporary) — exact text/language/speaker reaching TTS, before any provider call.
    # _safe_console() guards against a Hindi/Devanagari question crashing this print on a
    # non-UTF-8 Windows console codepage (same class of bug fixed for [TURN DEBUG]).
    print(f"[TTS DEBUG] incoming text={_safe_console(body.text)!r} | language={body.language!r} | "
          f"speaker_name={body.speaker_name!r} speaker_gender={body.speaker_gender!r} "
          f"speaker_sarvam={body.speaker_sarvam!r} speaker_rumik={body.speaker_rumik!r}", flush=True)
    print(f"[TTS DEBUG] member={(body.speaker_name or '(unnamed)')!r} gender={voice_config['gender']!r} "
          f"-> speaker={voice_config['sarvam_speaker']!r} (sarvam) / {voice_config['rumik_speaker']!r} (rumik)",
          flush=True)
    _t_request_start = time.perf_counter()

    if ELEVENLABS_API_KEY and not circuit_is_open("elevenlabs_tts"):
        _t0 = time.perf_counter()
        try:
            audio_bytes = await _elevenlabs_tts_audio(body.text)
            _ms = (time.perf_counter() - _t0) * 1000
            circuit_record_success("elevenlabs_tts")
            print(f"[TTS DEBUG] PROVIDER USED: ElevenLabs (success) | elevenlabs_ms={_ms:.0f} | total_ms={(time.perf_counter() - _t_request_start) * 1000:.0f}", flush=True)
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
        except Exception as e:
            _ms = (time.perf_counter() - _t0) * 1000
            tripped = circuit_record_failure("elevenlabs_tts", str(e))
            print(f"[TTS DEBUG] ElevenLabs FAILED: {e} | elevenlabs_ms={_ms:.0f}"
                  + (" | CIRCUIT TRIPPED (skipping for 10min)" if tripped else ""), flush=True)
            logger.warning("ElevenLabs TTS failed, trying Rumik: %s", e)
    elif ELEVENLABS_API_KEY:
        print("[TTS DEBUG] ElevenLabs SKIPPED (circuit open)", flush=True)
    else:
        print("[TTS DEBUG] ElevenLabs SKIPPED: no ELEVENLABS_API_KEY in .env", flush=True)

    if RUMIK_API_KEY and not circuit_is_open("rumik_tts"):
        _t0 = time.perf_counter()
        try:
            audio_bytes = await _rumik_tts_audio(body.text, voice_config)
            _ms = (time.perf_counter() - _t0) * 1000
            circuit_record_success("rumik_tts")
            print(f"[TTS DEBUG] PROVIDER USED: Rumik Silk (success) | speaker={voice_config['rumik_speaker']!r} gender={voice_config['gender']!r} | rumik_ms={_ms:.0f} | total_ms={(time.perf_counter() - _t_request_start) * 1000:.0f}", flush=True)
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
        except Exception as e:
            _ms = (time.perf_counter() - _t0) * 1000
            tripped = circuit_record_failure("rumik_tts", str(e))
            print(f"[TTS DEBUG] Rumik FAILED: {e} | rumik_ms={_ms:.0f}"
                  + (" | CIRCUIT TRIPPED (skipping for 10min)" if tripped else ""), flush=True)
            logger.warning("Rumik TTS failed, trying Sarvam: %s", e)
    elif RUMIK_API_KEY:
        print("[TTS DEBUG] Rumik SKIPPED (circuit open)", flush=True)
    else:
        print("[TTS DEBUG] Rumik SKIPPED: no RUMIK_API_KEY in .env", flush=True)

    if SARVAM_API_KEY:
        _t0 = time.perf_counter()
        try:
            lang_code = "hi-IN" if (body.language or "").lower() == "hindi" else "en-IN"
            print(f"[TTS DEBUG] Calling Sarvam with target_language_code={lang_code!r} speaker={voice_config['sarvam_speaker']!r} gender={voice_config['gender']!r} model='bulbul:v3'", flush=True)
            audio_bytes = await _sarvam_tts_audio(body.text, body.language, voice_config)
            _ms = (time.perf_counter() - _t0) * 1000
            _total_ms = (time.perf_counter() - _t_request_start) * 1000
            circuit_record_success("sarvam_tts")
            print(f"[TTS DEBUG] PROVIDER USED: Sarvam Bulbul (success) | speaker={voice_config['sarvam_speaker']!r} gender={voice_config['gender']!r} | sarvam_ms={_ms:.0f} | total_ms={_total_ms:.0f}", flush=True)
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
        except Exception as e:
            _ms = (time.perf_counter() - _t0) * 1000
            tripped = circuit_record_failure("sarvam_tts", str(e))
            print(f"[TTS DEBUG] Sarvam FAILED: {e} | sarvam_ms={_ms:.0f}"
                  + (" | CIRCUIT TRIPPED (skipping for 10min)" if tripped else ""), flush=True)
            logger.warning("Sarvam TTS failed: %s", e)
    else:
        print("[TTS DEBUG] Sarvam SKIPPED: no SARVAM_API_KEY in .env", flush=True)

    _total_ms = (time.perf_counter() - _t_request_start) * 1000
    print(f"[TTS DEBUG] ALL PROVIDERS EXHAUSTED | total_ms={_total_ms:.0f} — returning 500, frontend will fall back to browser speechSynthesis", flush=True)
    raise HTTPException(status_code=500, detail="No TTS provider available; use browser speechSynthesis")


# ============== RESUME PARSING ==============
@api_router.post("/resume/parse")
async def parse_resume(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Extract text from PDF resume and parse via Gemini (call_gemini) into structured JSON."""
    try:
        from pypdf import PdfReader
        contents = await file.read()
        logger.info(
            "RESUME UPLOAD RECEIVED | user_id=%s email=%s filename=%s size_bytes=%d",
            user["id"], user.get("email"), file.filename, len(contents),
        )
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Resume too large (max 5MB)")
        reader = PdfReader(io.BytesIO(contents))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        logger.info(
            "RESUME RAW TEXT | user_id=%s filename=%s text_len=%d first_800_chars=%r",
            user["id"], file.filename, len(text), text[:800],
        )
        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail="Could not extract any text from this PDF. If your resume's text is inside an image "
                       "or graphic (e.g. a scanned copy or a design-heavy template), pypdf cannot read it - "
                       "try a text-based PDF (exported directly from Word/Google Docs) instead.",
            )
        prompt = """You are a precise resume parser for an Indian campus-placement platform.
Parse the resume text into JSON. Return ONLY valid JSON, no markdown, with EXACTLY this shape:
{"name":"","email":"","phone":"","skills":[],"education":[{"degree":"","institution":"","year":""}],"experience":[{"title":"","company":"","duration":"","description":""}],"projects":[{"name":"","description":"","tech":[]}],"achievements":[],"years_of_experience":0}
Rules:
- name: take the candidate's name ONLY from the top/header of the resume text (it is almost always the very
  first line or the largest/most prominent text at the start). Do NOT infer the name from an email address,
  a project title, a company name, or any other field. If you cannot confidently identify a clear person's
  name at the top of the resume, return name as an empty string "" - do NOT guess or invent a name.
- skills: normalize names (e.g. "HTML/CSS" -> "HTML", "CSS"), no duplicates.
- projects.description: 1-2 sentences capturing what it does and any real-world usage or measurable result.
- years_of_experience: total professional experience as a number; internships count as their actual duration (3-month internship = 0.25).
- Do not invent anything not present in the resume."""

        def _mock_resume_response(_msg: str) -> str:
            # Deterministic mock-safe fallback matching the resume-parse shape (NOT the interview-turn shape)
            return json.dumps({
                "name": user.get("full_name") or "", "email": user.get("email") or "", "phone": "",
                "skills": [], "education": [], "experience": [], "projects": [], "achievements": [],
                "years_of_experience": 0, "is_mock": True,
            })

        raw = await call_gemini(prompt, f"Resume text:\n{text[:6000]}", f"resume-{user['id']}", mock_fn=_mock_resume_response)
        parsed = _parse_json_loose(raw)
        logger.info("RESUME LLM RAW RESPONSE | user_id=%s filename=%s raw=%r", user["id"], file.filename, raw)
        logger.info(
            "RESUME PARSED JSON | user_id=%s filename=%s parsed=%s is_mock=%s",
            user["id"], file.filename, json.dumps(parsed, ensure_ascii=False) if isinstance(parsed, dict) else parsed,
            isinstance(parsed, dict) and parsed.get("is_mock", False),
        )
        old_resume = user.get('resume_parsed_data') or {}
        old_name = old_resume.get('name') if isinstance(old_resume, dict) else None
        old_filename = user.get('resume_filename')
        new_name = parsed.get("name") if isinstance(parsed, dict) else None
        # Save resume metadata to user. This UNCONDITIONALLY OVERWRITES any previous resume -
        # $set always replaces these fields, it never merges with or preserves the old value.
        # NOTE: the account's own full_name (login/profile identity) is intentionally left
        # untouched here. The interview prompt (build_interview_system_prompt) already reads
        # the candidate's name from resume_parsed_data.name with priority over full_name, so
        # personalization still works - but the account itself stays reusable across resumes
        # (e.g. a shared/demo account testing multiple candidates' resumes one after another).
        update_fields = {
            "resume_filename": file.filename,
            "resume_parsed_data": parsed,
            "resume_uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await db.users.update_one({"id": user["id"]}, {"$set": update_fields})
        logger.info(
            "RESUME UPLOAD | user_id=%s email=%s | OLD: filename=%s name=%s -> NEW: filename=%s name=%s "
            "| text_len=%d matched=%d modified=%d",
            user["id"], user.get("email"), old_filename, old_name, file.filename, new_name,
            len(text), result.matched_count, result.modified_count,
        )
        return {"filename": file.filename, "parsed": parsed, "text_length": len(text)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Resume parse failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Resume parse failed: {str(e)[:200]}")


# ============== PDF REPORT ==============
@api_router.get("/sessions/{session_id}/report.pdf")
async def session_report_pdf(session_id: str, user=Depends(get_current_user)):
    """Generate a beautifully formatted PDF report for an interview session."""
    sess = await db.sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.colors import HexColor, white
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm)

        navy = HexColor("#0F1B3D")
        gold = HexColor("#B8962E")
        gold_light = HexColor("#D4AF55")
        muted = HexColor("#5B6B8C")

        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=26, textColor=navy, spaceAfter=4)
        h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, textColor=navy, spaceBefore=12, spaceAfter=6)
        small = ParagraphStyle("small", parent=styles["Normal"], fontName="Helvetica", fontSize=9, textColor=muted)
        body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=10, textColor=navy, leading=14)
        gold_tag = ParagraphStyle("gold", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, textColor=gold)

        score = float(sess.get("overall_score") or 7.5)
        verdict = "EXCELLENT" if score >= 8 else "STRONG" if score >= 7 else "GOOD" if score >= 6 else "NEEDS PRACTICE"

        story = []
        # Header
        story.append(Paragraph("MITHARVA AI", ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=12, textColor=gold)))
        story.append(Paragraph("Interview Performance Report", h1))
        s_type = sess.get("session_type", "").upper()
        sub = (sess.get("sub_type") or "").replace("_", " ").title()
        story.append(Paragraph(f"{s_type} — {sub}", small))
        date = (sess.get("completed_at") or sess.get("created_at") or "")[:10]
        story.append(Paragraph(f"Date: {date}  •  Duration: {round((sess.get('duration_seconds') or 0)/60)} min  •  Questions: {sess.get('questions_count') or len(sess.get('transcript') or [])}", small))
        story.append(Spacer(1, 6*mm))

        # Score block
        score_table = Table([
            [Paragraph(f"<font size=42 color='#B8962E'><b>{score:.1f}</b></font><br/><font size=8 color='#5B6B8C'>OUT OF 10</font>", body),
             Paragraph(f"<font size=10 color='#5B6B8C'>OVERALL VERDICT</font><br/><font size=16 color='#0F1B3D'><b>{verdict}</b></font><br/><br/><font size=9 color='#5B6B8C'>Better than 78% of users this month</font>", body)]
        ], colWidths=[55*mm, 110*mm])
        score_table.setStyle(TableStyle([
            ("BOX", (0,0), (-1,-1), 1.2, gold),
            ("BACKGROUND", (0,0), (-1,-1), HexColor("#FBF6E6")),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0), (-1,-1), 14),
            ("RIGHTPADDING", (0,0), (-1,-1), 14),
            ("TOPPADDING", (0,0), (-1,-1), 14),
            ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 8*mm))

        # Dimension scores
        story.append(Paragraph("Skill Dimensions", h2))
        dims = [
            ("Technical Accuracy", sess.get("technical_score")),
            ("Communication Clarity", sess.get("clarity_score")),
            ("Structure", sess.get("structure_score")),
            ("Confidence", sess.get("confidence_score")),
            ("Current Affairs", sess.get("current_affairs_score")),
            ("Domain Knowledge", sess.get("domain_score")),
        ]
        dim_rows = [["Dimension", "Score", "Bar"]]
        for label, v in dims:
            v = float(v or 0)
            filled = "█" * int(v) + "░" * (10 - int(v))
            dim_rows.append([label, f"{v:.1f} / 10", filled])
        dt = Table(dim_rows, colWidths=[60*mm, 30*mm, 75*mm])
        dt.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), navy),
            ("TEXTCOLOR", (0,0), (-1,0), gold),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
            ("FONTSIZE", (0,0), (-1,-1), 9.5),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [white, HexColor("#FAF7EF")]),
            ("TEXTCOLOR", (1,1), (1,-1), gold),
            ("FONTNAME", (1,1), (1,-1), "Helvetica-Bold"),
            ("TEXTCOLOR", (2,1), (2,-1), gold_light),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LINEBELOW", (0,0), (-1,0), 0.5, gold),
        ]))
        story.append(dt)
        story.append(Spacer(1, 6*mm))

        # Transcript
        transcript = sess.get("transcript") or []
        if transcript:
            story.append(Paragraph("Question & Answer Transcript", h2))
            for i, m in enumerate(transcript[:30]):
                role = m.get("role", "")
                speaker = m.get("speaker") or ("AI Interviewer" if role == "assistant" else "You")
                text = (m.get("text") or "")[:1200]
                color = "#B8962E" if role == "assistant" else "#243470"
                story.append(Paragraph(f"<b><font color='{color}'>{speaker}</font></b>", body))
                story.append(Paragraph(text, body))
                story.append(Spacer(1, 3*mm))

        # Action Plan
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph("3-Week Action Plan", h2))
        plan = [
            ("Week 1 — Confidence Building", "Record yourself answering 3 questions daily."),
            ("Week 2 — Reduce Filler Words", "Pause 2 seconds before starting each answer."),
            ("Week 3 — Current Affairs Depth", "Read 1 Hindu editorial + discuss with AI daily."),
        ]
        for title, body_t in plan:
            story.append(Paragraph(f"<b>{title}</b>", body))
            story.append(Paragraph(f"→ {body_t}", small))
            story.append(Spacer(1, 2*mm))

        story.append(Spacer(1, 8*mm))
        story.append(Paragraph("— अभ्यासेन सिद्धिः — Excellence through Practice —", gold_tag))
        story.append(Paragraph("Generated by Mitharva AI • mitharva.ai", small))

        doc.build(story)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="mitharva-report-{session_id[:8]}.pdf"'
        })
    except Exception as e:
        logger.exception("PDF report failed: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)[:200]}")


# ============== ONBOARDING ==============
class OnboardingIn(BaseModel):
    preparation_stage: Optional[str] = None
    previous_attempts: Optional[str] = None
    challenges: Optional[List[str]] = None
    preferred_language: Optional[str] = None


@api_router.post("/profile/onboarding")
async def save_onboarding(body: OnboardingIn, user=Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["onboarding_completed"] = True
    updates["onboarding_completed_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password": 0})
    return fresh


# ============== HEALTH ==============
@api_router.get("/")
async def root():
    return {"message": "Mitharva AI API", "version": "1.0.0"}


@api_router.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
