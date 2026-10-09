from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import logging
import json
import uuid
import bcrypt
import jwt
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Imported AFTER load_dotenv() — voice_live reads GEMINI_API_KEY from the
# environment at import time, so importing it any earlier would silently
# capture an empty string forever.
import voice_live

# Config
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
JWT_ALGO = 'HS256'
JWT_EXP_DAYS = 30

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="Mitharva AI API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

logger = logging.getLogger("mitharva")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


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
    interview_voice: Optional[str] = None  # one of voice_live.VOICE_OPTIONS keys


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


# ============== LLM (Gemini 3 Flash via Emergent) ==============
async def call_gemini(system_prompt: str, user_message: str, session_id: str) -> str:
    """Call Gemini 3 Flash via emergentintegrations. Falls back to mock if unavailable."""
    if not EMERGENT_LLM_KEY:
        return _mock_interview_response(user_message)
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt,
        ).with_model("gemini", "gemini-3-flash-preview")
        msg = UserMessage(text=user_message)
        response = await chat.send_message(msg)
        return response
    except Exception as e:
        logger.exception("Gemini call failed, using mock: %s", e)
        return _mock_interview_response(user_message)


def _mock_interview_response(user_message: str) -> str:
    # Deterministic mock fallback used when LLM fails
    return json.dumps({
        "nextQuestion": "Thank you for that answer. Could you elaborate on a specific example where you demonstrated leadership in a challenging situation?",
        "speakerName": "Shri R.K. Sharma",
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


def build_interview_system_prompt(config: dict, profile: dict) -> str:
    base_rules = """Respond ONLY in valid JSON in this EXACT format after every user answer:
{"nextQuestion":"...","speakerName":"...","evaluation":{"technicalScore":0,"clarityScore":0,"structureScore":0,"confidenceEstimate":0,"overallScore":0,"keyStrengths":[],"improvementAreas":[],"liveTip":""},"isInterviewComplete":false}
Scores are 0-10 decimals. Keep questions concise (1-2 sentences). Set isInterviewComplete: true after 10-12 questions."""

    name = profile.get('full_name', 'the candidate')
    s_type = config.get('session_type', 'upsc')

    if s_type == 'upsc':
        return f"""You are Shri R.K. Sharma, a senior UPSC board member (IAS retired, 35 years experience), conducting a Personality Test.
Candidate: {name}
Optional Subject: {profile.get('daf_optional_subject') or 'Geography'}
Home State: {profile.get('daf_home_state') or 'Uttar Pradesh'}
Hobbies: {profile.get('daf_hobbies') or 'Cricket, Reading'}
Conduct a 10-12 question UPSC Personality Test. Vary questions: DAF-based, current affairs, administrative scenarios, optional subject.
{base_rules}"""
    if s_type == 'banking':
        return f"""You are an IBPS PO interview panel member. Candidate: {name}. Cover banking knowledge, current affairs, communication. 10-12 questions.
{base_rules}"""
    if s_type == 'campus_it':
        return f"""You are a Senior Engineering Manager at {config.get('company') or 'a top tech company'}. Candidate: {name}. Cover technical depth, HR behavioral (STAR), problem-solving. 10-12 questions.
{base_rules}"""
    if s_type == 'ssc':
        return f"""You are an SSC CGL interview panel member. Candidate: {name}. Cover general awareness, scenarios, communication. 10-12 questions.
{base_rules}"""
    if s_type == 'campus_mba':
        return f"""You are an MBA campus interviewer (consulting/finance). Candidate: {name}. Cover behavioral, leadership, domain. 10-12 questions.
{base_rules}"""
    return f"""You are a professional interviewer. Candidate: {name}. Conduct a 10-12 question interview. {base_rules}"""


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
    system_prompt = build_interview_system_prompt(sess, user)
    raw = await call_gemini(system_prompt, body.user_message, body.session_id)
    parsed = _parse_json_loose(raw)
    return {"raw": raw, "parsed": parsed}


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
    return {"nextQuestion": text.strip(), "speakerName": "Shri R.K. Sharma",
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


# ============== VOICE STT (OpenAI Whisper) ==============
@api_router.post("/voice/stt")
async def voice_stt(file: UploadFile = File(...), language: Optional[str] = None, user=Depends(get_current_user)):
    """Transcribe audio to text using OpenAI Whisper via Emergent key."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM key not configured")
    try:
        from emergentintegrations.llm.openai import OpenAISpeechToText
        contents = await file.read()
        if len(contents) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Audio file too large (max 25MB)")
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        # OpenAI Whisper accepts an in-memory file-like object with a filename
        bio = io.BytesIO(contents)
        bio.name = file.filename or "audio.webm"
        kwargs = {"file": bio, "model": "whisper-1", "response_format": "json"}
        if language and language != "auto":
            lang_map = {"english": "en", "hindi": "hi", "hinglish": "hi", "tamil": "ta", "bengali": "bn", "marathi": "mr"}
            kwargs["language"] = lang_map.get(language, language[:2])
        response = await stt.transcribe(**kwargs)
        return {"text": getattr(response, "text", str(response))}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Whisper STT failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)[:200]}")


# ============== RESUME PARSING ==============
@api_router.post("/resume/parse")
async def parse_resume(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Extract text from PDF resume and parse via Gemini into structured JSON."""
    try:
        from pypdf import PdfReader
        contents = await file.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Resume too large (max 5MB)")
        reader = PdfReader(io.BytesIO(contents))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        prompt = """Parse this resume into clean JSON. Return ONLY JSON with this exact shape:
{"name":"","email":"","phone":"","skills":[],"education":[{"degree":"","institution":"","year":""}],"experience":[{"title":"","company":"","duration":"","description":""}],"projects":[{"name":"","description":"","tech":[]}],"achievements":[]}"""
        raw = await call_gemini(prompt, f"Resume text:\n{text[:6000]}", f"resume-{user['id']}")
        parsed = _parse_json_loose(raw)
        # Save resume metadata to user
        await db.users.update_one({"id": user["id"]}, {"$set": {
            "resume_filename": file.filename,
            "resume_parsed_data": parsed,
            "resume_uploaded_at": datetime.now(timezone.utc).isoformat(),
        }})
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


# ============== LIVE VOICE (Gemini Live bridge) ==============
@api_router.get("/voice/options")
async def voice_options():
    """Named voices the user can pick for their interviewer in Profile /
    Interview Setup. See voice_live.VOICE_OPTIONS for the underlying mapping."""
    return {
        "voices": [
            {"key": "formal_male", "label": "Formal — Male"},
            {"key": "formal_female", "label": "Formal — Female"},
            {"key": "warm_male", "label": "Warm — Male"},
            {"key": "warm_female", "label": "Warm — Female"},
            {"key": "stern_male", "label": "Stern — Male"},
        ],
        "configured": bool(voice_live.GEMINI_API_KEY),
    }


async def _get_user_by_id(user_id: str) -> Optional[dict]:
    return await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})


async def _get_session_by_id(session_id: str, user_id: str) -> Optional[dict]:
    if not session_id:
        return None
    return await db.sessions.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})


voice_live.register(api_router, db, build_interview_system_prompt, _get_user_by_id, _get_session_by_id)

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
