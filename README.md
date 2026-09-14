<div align="center">

<img src="frontend/public/logo.png" alt="Mitharva AI Logo" width="80" />

# MITHARVA AI

### *अभ्यासेन सिद्धिः — Excellence through Practice*

**India's first AI-powered interview preparation platform**  
*For UPSC · SSC · Banking · Railway · Campus Placements*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.1-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19.0-61DAFB?style=flat-square&logo=react)](https://react.dev/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Motor_3.3-47A248?style=flat-square&logo=mongodb)](https://www.mongodb.com/)
[![TailwindCSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC?style=flat-square&logo=tailwindcss)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/Tests-44%2F44_Passing-brightgreen?style=flat-square)](#testing)
[![License](https://img.shields.io/badge/License-Proprietary-navy?style=flat-square)](#license)

</div>

---

## Table of Contents

1. [What is Mitharva AI?](#1-what-is-mitharva-ai)
2. [Repository Structure](#2-repository-structure)
3. [Tech Stack](#3-tech-stack)
4. [System Architecture](#4-system-architecture)
5. [Backend — Deep Dive](#5-backend--deep-dive)
6. [Frontend — Deep Dive](#6-frontend--deep-dive)
7. [Design System & Theming](#7-design-system--theming)
8. [Build & Dev Tooling](#8-build--dev-tooling)
9. [Environment Variables](#9-environment-variables)
10. [Local Setup — Step by Step](#10-local-setup--step-by-step)
11. [API Reference](#11-api-reference)
12. [Database Schema](#12-database-schema)
13. [Authentication Flow](#13-authentication-flow)
14. [Interview Session Lifecycle](#14-interview-session-lifecycle)
15. [AI & LLM Architecture](#15-ai--llm-architecture)
16. [Voice & Speech Pipeline](#16-voice--speech-pipeline)
17. [Subscription & Billing](#17-subscription--billing)
18. [Testing](#18-testing)
19. [Seed Data & Demo Credentials](#19-seed-data--demo-credentials)
20. [Deployment Notes](#20-deployment-notes)
21. [Roadmap](#21-roadmap)

---

## 1. What is Mitharva AI?

Mitharva AI is a **production-grade, full-stack AI interview preparation platform** built for India's massive population of government exam aspirants and campus placement candidates. It gives any student — from a Tier-3 city with no coaching access — the same preparation quality previously available only at expensive Delhi institutes.

### Who it serves

| Candidate | Exam | What Mitharva AI provides |
|---|---|---|
| UPSC aspirant | Civil Services Personality Test | DAF-personalized mock, board-style 3-AI panel, current affairs Q generation |
| SSC/Banking candidate | CGL, IBPS PO, SBI PO | Role-specific mock interview, situational & domain questions |
| Engineering student | TCS, Amazon, Google, Microsoft | Technical depth, STAR behavioral, system design interview practice |
| Railway aspirant | RRB NTPC, Group D | General awareness, role-based situational practice |
| MBA student | HR Round, Case Interview | Leadership behavioral, consulting/finance domain |

### Why it exists

- India's UPSC coaching institutes charge ₹3,000–5,000 per single mock interview session
- 4,200+ engineering colleges produce 1.5 million graduates annually — most have no AI interview prep tools
- Every existing global platform (FinalRoundAI, Intervyo, Yoodli) is English-only, USD-priced, and built for Western markets
- No platform supports Hindi voice AI, UPSC DAF personalization, or Indian government exam patterns

---

## 2. Repository Structure

```
Mitharava-AI/
│
├── backend/                          # Python FastAPI application
│   ├── server.py                     # All 19 API endpoints — single-file backend
│   ├── requirements.txt              # Python dependencies (pinned versions)
│   └── tests/
│       ├── test_mitharva_backend.py  # 31 core API tests
│       └── test_deferred_endpoints.py# 13 tests for STT, PDF, resume, onboarding
│
├── frontend/                         # React 19 single-page application
│   ├── public/
│   │   ├── index.html                # HTML shell — page title, meta description, font preconnect
│   │   ├── logo.png                  # Brand logo — navy + gold (used in dark mode)
│   │   └── logo-light.png            # Light mode logo variant
│   │
│   ├── src/
│   │   ├── App.js                    # Root component — ThemeProvider > AuthProvider > BrowserRouter > 13 routes
│   │   ├── App.css                   # Single rule: .App { min-height: 100vh }
│   │   ├── index.js                  # ReactDOM.createRoot entry point (StrictMode)
│   │   ├── index.css                 # Full design system: CSS variables, animations, brand utilities
│   │   │
│   │   ├── lib/
│   │   │   ├── api.js                # Axios instance — REACT_APP_BACKEND_URL base, JWT interceptor
│   │   │   ├── auth.jsx              # AuthContext — user state, login/signup/logout/refresh/updateUser
│   │   │   ├── theme.jsx             # ThemeContext — dark/light toggle, localStorage persistence
│   │   │   └── utils.js             # cn() = clsx + tailwind-merge helper
│   │   │
│   │   ├── hooks/
│   │   │   └── use-toast.js          # Sonner toast hook wrapper
│   │   │
│   │   ├── components/
│   │   │   ├── BrandLogo.jsx         # Logo + wordmark + optional tagline
│   │   │   ├── DashboardLayout.jsx   # Sidebar (260px) + main content flex layout
│   │   │   ├── Footer.jsx            # 5-column footer — brand, Product, Resources, Company + socials
│   │   │   ├── Navbar.jsx            # Fixed glassmorphism navbar — scroll-reactive shadow
│   │   │   ├── OnboardingWizard.jsx  # 3-step first-visit modal — POST /api/profile/onboarding
│   │   │   ├── ParticleField.jsx     # Animated gold particle canvas for hero backgrounds
│   │   │   ├── ProtectedRoute.jsx    # JWT auth guard — spinner while loading, redirect if unauth
│   │   │   ├── PublicLayout.jsx      # Navbar + children + Footer wrapper
│   │   │   ├── RoleSwitcher.jsx      # Exam focus dropdown — 6 options, PATCH /api/profile live
│   │   │   ├── Sidebar.jsx           # Dashboard left nav — ReadinessRing SVG, user card, plan badge
│   │   │   ├── ThemeToggle.jsx       # Sun/Moon icon button — dark/light toggle
│   │   │   └── ui/                   # shadcn/ui components (40+ primitives — Radix UI based)
│   │   │       ├── accordion.jsx, alert.jsx, alert-dialog.jsx, aspect-ratio.jsx
│   │   │       ├── avatar.jsx, badge.jsx, breadcrumb.jsx, button.jsx, calendar.jsx
│   │   │       ├── card.jsx, carousel.jsx, checkbox.jsx, collapsible.jsx, command.jsx
│   │   │       ├── context-menu.jsx, dialog.jsx, drawer.jsx, dropdown-menu.jsx
│   │   │       ├── form.jsx, hover-card.jsx, input-otp.jsx, input.jsx, label.jsx
│   │   │       ├── menubar.jsx, navigation-menu.jsx, pagination.jsx, popover.jsx
│   │   │       ├── progress.jsx, radio-group.jsx, resizable.jsx, scroll-area.jsx
│   │   │       ├── select.jsx, separator.jsx, sheet.jsx, skeleton.jsx, slider.jsx
│   │   │       ├── sonner.jsx, switch.jsx, table.jsx, tabs.jsx, textarea.jsx
│   │   │       ├── toast.jsx, toaster.jsx, toggle.jsx, toggle-group.jsx, tooltip.jsx
│   │   │
│   │   └── pages/
│   │       ├── Landing.jsx           # Public homepage — 9 sections including hero, features, pricing preview
│   │       ├── About.jsx             # Mission, stats, team, tech sections
│   │       ├── Pricing.jsx           # Full pricing — 3 tiers + monthly/annual toggle + FAQ
│   │       ├── Signup.jsx            # Registration — all 37 Indian states dropdown, exam focus
│   │       ├── Login.jsx             # Login + one-click demo fill button
│   │       ├── Dashboard.jsx         # Analytics — line chart, radar, stat cards, session table
│   │       ├── InterviewSetup.jsx    # 5-step wizard — 8 exam categories, resume upload, config
│   │       ├── InterviewRoom.jsx     # 🌟 Live interview — orb, camera, 3-AI panel, analytics sidebar
│   │       ├── InterviewResults.jsx  # Animated score ring, radar, transcript, PDF download
│   │       ├── Practice.jsx          # Question bank — filters, AI feedback modal
│   │       ├── CurrentAffairs.jsx    # News digest — role-based tabs, AI question generation
│   │       ├── Profile.jsx           # 4-tab profile editor
│   │       └── Subscription.jsx      # Plan management — usage bar, mock payment, billing history
│   │
│   ├── plugins/
│   │   └── health-check/
│   │       ├── health-endpoints.js   # 6 Express endpoints: /health, /health/simple, /health/ready,
│   │       │                         # /health/live, /health/errors, /health/stats
│   │       └── webpack-health-plugin.js # Webpack plugin — tracks compile state, errors, timing
│   │
│   ├── package.json                  # Dependencies + scripts (start/build/test via CRACO)
│   ├── tailwind.config.js            # Custom colors (navy/gold), fonts, keyframe animations
│   ├── craco.config.js               # CRA override: @/ alias, health check opt-in, visual-edits
│   ├── jsconfig.json                 # Path alias @/ → src/
│   ├── components.json               # shadcn/ui config — new-york style, lucide icons
│   └── postcss.config.js             # Tailwind + autoprefixer
│
├── memory/
│   └── PRD.md                        # Product Requirements Document — full build history & iteration log
│
├── test_reports/
│   ├── iteration_1.json              # Test snapshot from iteration 1
│   ├── iteration_2.json              # Test snapshot from iteration 2
│   └── pytest/
│       ├── pytest_results.xml        # Core test XML results
│       └── deferred_results.xml      # Deferred endpoints XML results
│
├── tests/
│   └── __init__.py                   # Root-level test package init
│
├── test_result.md                    # Multi-agent testing protocol & task status tracking
├── .gitconfig                        # Repo-level git identity
└── .gitignore                        # Comprehensive — .env, node_modules, venv, builds, caches
```

---

## 3. Tech Stack

### Backend

| Technology | Version | Role |
|---|---|---|
| **FastAPI** | 0.110.1 | Async web framework — all REST API endpoints |
| **Motor** | 3.3.1 | Async MongoDB driver (wraps PyMongo) |
| **Pydantic** | 2.13.4 | Request/response data validation and serialization |
| **bcrypt** | 4.1.3 | Password hashing |
| **PyJWT** | 2.12.1 | JWT token creation and verification (HS256) |
| **python-dotenv** | 1.2.2 | `.env` loading |
| **Uvicorn** | 0.25.0 | ASGI production server |
| **Starlette CORSMiddleware** | 0.37.2 | CORS handling |
| **openai** | 1.99.9 | OpenAI SDK — Whisper STT |
| **pypdf** | 6.11.0 | PDF text extraction for resume parsing |
| **reportlab** | 4.5.1 | PDF report generation with branded layout |
| **email-validator** | 2.3.0 | Email format validation via Pydantic `EmailStr` |
| **python-multipart** | 0.0.28 | Multipart form parsing for file uploads |
| **google-generativeai** | 0.8.6 | Google AI SDK (underlying Gemini integration) |
| **openai** | 1.99.9 | OpenAI SDK (for Whisper STT) |

### Frontend

| Technology | Version | Role |
|---|---|---|
| **React** | 19.0 | Component-based SPA framework |
| **React Router DOM** | 7.5.1 | Client-side routing with `<BrowserRouter>` |
| **Tailwind CSS** | 3.4.17 | Utility-first styling with custom brand tokens |
| **shadcn/ui** | new-york style | 40+ accessible UI components (Radix UI primitives) |
| **Radix UI** | various | Headless accessible components backing shadcn |
| **Axios** | 1.8.4 | HTTP client — interceptors for JWT auth + 401 handling |
| **Recharts** | 3.6.0 | Line chart (score progress) + Radar chart (6 dimensions) |
| **Sonner** | 2.0.3 | Toast notifications (positioned top-right, rich colors) |
| **React Hook Form** | 7.56.2 | Form state management |
| **Zod** | 3.24.4 | Form schema validation |
| **Lucide React** | 0.507.0 | Icon library |
| **next-themes** | 0.4.6 | Theme system base (extended with custom ThemeContext) |
| **date-fns** | 4.1.0 | Date formatting |
| **clsx + tailwind-merge** | 2.1.1 / 3.2.0 | Class name utility (`cn()`) |
| **CRACO** | 7.1.0 | CRA config override (webpack alias, health check plugin) |
| **tailwindcss-animate** | 1.0.7 | Tailwind animation utilities |

---

## 4. System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          CLIENT BROWSER                                │
│                                                                        │
│   React 19 SPA — 13 routes — ThemeProvider > AuthProvider > Router   │
│   Tailwind CSS + shadcn/ui + Recharts + Sonner                        │
│                                                                        │
│   ┌────────────┐  ┌────────────────┐  ┌───────────────────────────┐   │
│   │ Public     │  │ Protected      │  │ InterviewRoom (standalone)│   │
│   │ Landing    │  │ Dashboard      │  │ Full-screen, no layout    │   │
│   │ About      │  │ Setup + Room   │  │ 3-column grid             │   │
│   │ Pricing    │  │ Results        │  │ Camera + Orb + Panel      │   │
│   │ Auth       │  │ Practice       │  └───────────────────────────┘   │
│   └────────────┘  └────────────────┘                                  │
│                                                                        │
│   lib/api.js (Axios) — baseURL=REACT_APP_BACKEND_URL/api               │
│   JWT token: localStorage key "mitharva_token"                        │
└─────────────────────────────┬──────────────────────────────────────────┘
                              │ HTTPS REST (JSON)
                              │ Authorization: Bearer <JWT>
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND (server.py)                       │
│                                                                        │
│   APIRouter prefix: /api                                               │
│   CORS: configurable via CORS_ORIGINS env var                         │
│   Auth: HTTPBearer → jwt.decode → db.users lookup → Depends injection │
│                                                                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐  │
│  │  /auth/*     │ │ /sessions/*  │ │ /practice/*  │ │ /profile/*  │  │
│  │  signup      │ │ create       │ │ feedback     │ │ PATCH       │  │
│  │  login       │ │ list/get     │ │              │ │ onboarding  │  │
│  │  me          │ │ turn (LLM)   │ └──────────────┘ └─────────────┘  │
│  └──────────────┘ │ complete     │                                    │
│                   │ report.pdf   │ ┌──────────────┐ ┌─────────────┐  │
│  ┌──────────────┐ └──────────────┘ │ /questions   │ │/subscription│  │
│  │ /voice/stt   │                  │ GET (filter) │ │ mock-pay    │  │
│  │ Whisper API  │ ┌──────────────┐ └──────────────┘ │ history     │  │
│  └──────────────┘ │/current-     │                  └─────────────┘  │
│                   │affairs/*     │ ┌──────────────┐                   │
│  ┌──────────────┐ │ GET list     │ │/dashboard/   │                   │
│  │/resume/parse │ │ POST Qs gen  │ │ stats        │                   │
│  │pypdf+Gemini  │ └──────────────┘ └──────────────┘                   │
│  └──────────────┘                                                      │
└──────────┬──────────────────────────────────┬──────────────────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────┐           ┌───────────────────────────┐
│  MongoDB (Motor)    │           │  External AI APIs          │
│                     │           │                            │
│  db.users           │           │  External AI APIs:         │
│  db.sessions        │           │  ├── Gemini 3 Flash        │
│  db.questions       │           │  │   (LlmChat, stateful)  │
│  db.current_affairs │           │  └── OpenAI Whisper        │
│  db.billing_history │           │      (speech-to-text)      │
└─────────────────────┘           └───────────────────────────┘
```

### Application Bootstrap Sequence

```
1. Backend starts → uvicorn server:app
2. @app.on_event("startup") → seed_database()
   - Seeds 30 questions if db.questions is empty
   - Seeds 10 current affairs if db.current_affairs is empty
   - Seeds demo user + 12 sessions if demo@mitharva.ai doesn't exist
3. Frontend starts → yarn start → CRACO webpack dev server
4. index.js → ReactDOM.createRoot → <App />
5. App renders: ThemeProvider → AuthProvider → BrowserRouter
6. AuthProvider useEffect → GET /api/auth/me (if mitharva_token in localStorage)
7. ThemeProvider reads localStorage "mitharva_theme" → applies dark/light class to <html>
```

---

## 5. Backend — Deep Dive

### `server.py` — Complete Structure

The entire backend lives in a single file (`backend/server.py`). It is organized in the following sections (marked with `# ====== SECTION ======` comments):

```
server.py sections:
├── IMPORTS & CONFIGURATION        — env loading, MongoDB client, JWT config
├── MODELS                         — 10 Pydantic request body models
├── AUTH HELPERS                   — hash_password, verify_password, create_token, get_current_user
├── LLM (Gemini 3 Flash)           — call_gemini, _mock_interview_response, build_interview_system_prompt
├── AUTH ROUTES                    — /auth/signup, /auth/login, /auth/me
├── PROFILE ROUTES                 — PATCH /profile
├── INTERVIEW SESSION ROUTES       — create, list, get, turn, complete
├── QUESTION BANK ROUTES           — GET /questions
├── PRACTICE ROUTES                — POST /practice/feedback
├── CURRENT AFFAIRS ROUTES         — GET /current-affairs, POST /current-affairs/questions
├── SUBSCRIPTION ROUTES            — mock-pay, history
├── DASHBOARD STATS                — GET /dashboard/stats
├── SEED DATA ON STARTUP           — 30 questions, 10 current affairs, demo user
├── VOICE STT                      — POST /voice/stt (Whisper)
├── RESUME PARSING                 — POST /resume/parse (pypdf + Gemini)
├── PDF REPORT                     — GET /sessions/{id}/report.pdf (ReportLab)
├── ONBOARDING                     — POST /profile/onboarding
└── HEALTH                         — GET /api/, GET /api/health
```

### Configuration Variables (top of `server.py`)

```python
MONGO_URL    = os.environ['MONGO_URL']         # Required — MongoDB connection string
DB_NAME      = os.environ['DB_NAME']           # Required — database name
JWT_SECRET   = os.environ.get('JWT_SECRET', 'change-me')   # JWT signing secret
LLM_API_KEY      = os.environ.get('LLM_API_KEY', '')      # Gemini + Whisper access
JWT_ALGO     = 'HS256'                         # Algorithm fixed in code
JWT_EXP_DAYS = 30                              # Token lifetime
```

### Pydantic Models

| Model | Fields | Used By |
|---|---|---|
| `SignupIn` | full_name, email, phone?, password, exam_focus?, state?, college? | POST /auth/signup |
| `LoginIn` | email, password | POST /auth/login |
| `ProfileUpdate` | 14 optional fields (all profile fields except email/password) | PATCH /profile |
| `SessionCreate` | session_type, sub_type?, duration_minutes, difficulty, language, mode, company? | POST /sessions |
| `TurnIn` | session_id, user_message, question_index | POST /sessions/turn |
| `CompleteSessionIn` | session_id, transcript[], duration_seconds, camera_used | POST /sessions/complete |
| `PracticeFeedbackIn` | question, answer, exam_type | POST /practice/feedback |
| `NewsQuestionsIn` | news_title, news_summary | POST /current-affairs/questions |
| `MockPaymentIn` | plan ('basic' or 'pro') | POST /subscription/mock-pay |
| `OnboardingIn` | preparation_stage?, previous_attempts?, challenges?[], preferred_language? | POST /profile/onboarding |

### `build_interview_system_prompt()` — Interview Persona Logic

This function selects the AI persona and injects the user's DAF profile:

```python
def build_interview_system_prompt(config: dict, profile: dict) -> str:
    base_rules = """Respond ONLY in valid JSON in this EXACT format:
{"nextQuestion":"...","speakerName":"...","evaluation":{
  "technicalScore":0,"clarityScore":0,"structureScore":0,
  "confidenceEstimate":0,"overallScore":0,
  "keyStrengths":[],"improvementAreas":[],"liveTip":""},
"isInterviewComplete":false}
Scores are 0-10 decimals. Set isInterviewComplete: true after 10-12 questions."""
```

| `session_type` | AI Persona | Profile Fields Injected |
|---|---|---|
| `upsc` | Shri R.K. Sharma (IAS retired, 35 years) | full_name, daf_optional_subject, daf_home_state, daf_hobbies |
| `banking` | IBPS PO interview panel member | full_name |
| `campus_it` | Senior Engineering Manager at `{company}` | full_name, company |
| `ssc` | SSC CGL interview panel member | full_name |
| `campus_mba` | MBA campus interviewer (consulting/finance) | full_name |
| any other | Professional interviewer (generic) | full_name |

### `_parse_json_loose()` — Fault-Tolerant LLM Response Parser

LLM output is not always clean JSON. This function handles it gracefully in 3 levels:

```python
def _parse_json_loose(text: str) -> dict:
    # Level 1: Direct json.loads
    # Level 2: Find first { and last } and parse substring
    # Level 3: Return safe default dict with overallScore: 7.0
```

### Score Aggregation in `complete_session`

When a session ends, the backend aggregates all per-question scores from the transcript:

```python
def avg(key):
    vals = [float(e.get(key, 0)) for e in evals if e.get(key) is not None]
    return round(sum(vals) / len(vals), 2) if vals else 7.0

update = {
    "overall_score": avg("overallScore"),
    "technical_score": avg("technicalScore"),
    "clarity_score": avg("clarityScore"),
    "structure_score": avg("structureScore"),
    "confidence_score": avg("confidenceEstimate"),
    "current_affairs_score": round(min(10, overall + 0.2), 2),  # derived
    "domain_score": round(min(10, overall + 0.3), 2),           # derived
}
```

### PDF Report Generation (`reportlab`)

The `GET /sessions/{id}/report.pdf` endpoint builds a fully branded A4 PDF in memory:

- **Colors**: Navy `#0F1B3D`, Gold `#B8962E`, Gold-light `#D4AF55`, Muted `#5B6B8C`
- **Layout**: Score block (overall score + verdict), 6-dimension bar table, full Q&A transcript (up to 30 messages), 3-week action plan, Sanskrit tagline watermark
- **Verdict logic**: EXCELLENT (≥8), STRONG (≥7), GOOD (≥6), NEEDS PRACTICE (<6)
- **Streaming**: Returns `StreamingResponse` with `Content-Disposition: attachment` header

### Seed Data

On every backend startup, `seed_database()` runs and inserts data only if the respective collection is empty:

**30 questions** across 5 categories:
- UPSC: 10 questions (10 hard situational + medium current affairs + easy factual)
- Banking: 5 questions (PSL norms, CRR/SLR, NARCL, JAM trinity, HR)
- Campus IT: 8 questions (team project, REST vs GraphQL, system design URL shortener, production incident)
- SSC: 4 questions (Income Tax Inspector priorities, integrity scenario)
- Campus MBA: 3 questions (resume walkthrough, management trainee scenario, leadership vs management)

**10 current affairs** (May 2026):
- RBI Monetary Policy (repo rate 6.25%), Digital India 2.0, 50-qubit Quantum Computer, Kharif MSP, India-Japan defence, Electoral Bonds transparency, Gaganyaan crew escape test, NEP 4-year report, CAD data, Agni-V MIRV test

**Demo user**: `demo@mitharva.ai` / `Demo@2026` with 12 pre-seeded completed sessions spanning 45 days of history

---

## 6. Frontend — Deep Dive

### Provider Hierarchy (`App.js`)

```jsx
<ThemeProvider>         // Custom ThemeContext — dark/light, localStorage "mitharva_theme"
  <AuthProvider>        // Custom AuthContext — user state, JWT in localStorage "mitharva_token"
    <BrowserRouter>
      <Routes>          // 13 routes (5 public + 8 protected)
        ...
      </Routes>
      <Toaster          // Sonner — position: top-right, richColors, closeButton, theme: dark
        position="top-right"
        richColors
        closeButton
        theme="dark"
      />
    </BrowserRouter>
  </AuthProvider>
</ThemeProvider>
```

### Route Map

| Path | Component | Layout | Auth |
|---|---|---|---|
| `/` | `Landing` | `PublicLayout` | ❌ |
| `/about` | `About` | `PublicLayout` | ❌ |
| `/pricing` | `Pricing` | `PublicLayout` | ❌ |
| `/auth/signup` | `Signup` | None (full-screen 2-col) | ❌ |
| `/auth/login` | `Login` | None (full-screen 2-col) | ❌ |
| `/dashboard` | `Dashboard` | `DashboardLayout` | ✅ JWT |
| `/interview/setup` | `InterviewSetup` | `DashboardLayout` | ✅ JWT |
| `/interview/room/:id` | `InterviewRoom` | None (standalone full-screen) | ✅ JWT |
| `/interview/results/:id` | `InterviewResults` | `DashboardLayout` | ✅ JWT |
| `/practice` | `Practice` | `DashboardLayout` | ✅ JWT |
| `/current-affairs` | `CurrentAffairs` | `DashboardLayout` | ✅ JWT |
| `/profile` | `Profile` | `DashboardLayout` | ✅ JWT |
| `/subscription` | `Subscription` | `DashboardLayout` | ✅ JWT |
| `*` (404) | `<Navigate to="/" />` | — | — |

### `lib/api.js` — Axios Instance

```js
export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const api = axios.create({ baseURL: API });

// REQUEST interceptor — attach JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("mitharva_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// RESPONSE interceptor — soft logout on 401
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem("mitharva_token");
    }
    return Promise.reject(err);
  }
);
```

### `lib/auth.jsx` — AuthContext

Provides these values to all components:

| Value | Type | Description |
|---|---|---|
| `user` | Object \| null | Current user profile (no password/\_id) |
| `loading` | Boolean | True while checking stored token on mount |
| `login(email, password)` | async fn | POST /auth/login → stores token → sets user |
| `signup(payload)` | async fn | POST /auth/signup → stores token → sets user |
| `logout()` | fn | Removes token from localStorage, clears user state |
| `refresh()` | async fn | GET /auth/me → refreshes user from backend |
| `updateUser(u)` | fn | Directly update user state (used after PATCH /profile) |

### `lib/theme.jsx` — ThemeContext

- Reads from `localStorage.getItem("mitharva_theme")` on init — defaults to `"dark"`
- On theme change: adds/removes `.dark` class on `document.documentElement`
- CSS variables in `index.css` use `:root` (light) and `.dark` (dark) selectors

### Sidebar — `ReadinessRing` Component

The sidebar contains a custom SVG-based circular progress ring:

```jsx
function ReadinessRing({ value }) {
  const r = 22, c = 2 * Math.PI * r;     // circumference
  const offset = c - (value / 100) * c;  // dash offset for progress
  return (
    <svg viewBox="0 0 56 56">
      <circle ... stroke="rgba(184,150,46,0.2)" />  {/* track */}
      <circle ... stroke="url(#ring-grad)" strokeDashoffset={offset} />  {/* fill */}
      {/* gold linear gradient */}
    </svg>
  );
}
```

Readiness score formula: `Math.min(95, 40 + total_interviews * 2)`

### `InterviewRoom.jsx` — The Flagship Component

This is the most complex component in the codebase. Key state:

```js
const [session, setSession]       // Loaded session object from /api/sessions/:id
const [transcript, setTranscript] // Array of { role, speaker, text, evaluation, ts }
const [orbState, setOrbState]     // "idle" | "listening" | "processing" | "speaking"
const [currentSpeaker, setCurrentSpeaker] // Index 0-2 into INTERVIEWERS array
const [timer, setTimer]           // Seconds elapsed — displayed as MM:SS
const [latestEval, setLatestEval] // Last question's evaluation object for sidebar
const [cameraOn, setCameraOn]     // Boolean — camera stream active
const [paused, setPaused]         // Pauses timer only (not the AI)
const [textMode, setTextMode]     // Text input instead of voice
const [whisperMode, setWhisperMode] // true=Whisper STT, false=browser SpeechRecognition
const [endConfirm, setEndConfirm] // End interview confirmation modal
```

The 3 AI panel members defined in code:
```js
const INTERVIEWERS = [
  { id: "chair",  name: "Shri R.K. Sharma",  role: "UPSC Chairman (IAS Retd.)", initials: "RK", color: "from-amber-400 to-yellow-700" },
  { id: "domain", name: "Dr. Priya Nambiar", role: "Domain Expert",              initials: "PN", color: "from-indigo-400 to-indigo-700" },
  { id: "legal",  name: "Adv. Mehul Desai",  role: "Legal Expert",               initials: "MD", color: "from-emerald-400 to-emerald-700" },
];
```

**Layout**: 3-column grid on large screens:
- Left (280px): AI panel cards with speaking indicator + wave bars
- Center (flex-1): Camera feed → Transcript → Voice bar
- Right (320px): Live analytics sidebar — question progress, score bars, live tip, body language, session stats

**Orb states**: CSS classes `.orb-idle`, `.orb-listening`, `.orb-processing`, `.orb-speaking` — each has a distinct animation (pulse, ripple, spin, fast-pulse)

**Auto-complete logic**: Interview ends automatically when `p.isInterviewComplete === true || qIndex >= 11` (5-second delay before redirect)

### `InterviewSetup.jsx` — 5-Step Wizard

| Step | What user does | Data set |
|---|---|---|
| 1 — Category | Pick 1 of 8 exam types | `session_type` |
| 2 — Sub-type | Pick sub-format for chosen exam | `sub_type` |
| 3 — Settings | Duration (15/20/30/45 min), Difficulty, Language, Mode (voice camera/voice/text) | `duration_minutes`, `difficulty`, `language`, `mode` |
| 4 — Resume | Upload PDF (optional, max 5MB) | Calls POST /resume/parse, shows skill chips |
| 5 — Review | Summary card + Begin button | Calls POST /sessions → navigate to /interview/room/:id |

Available categories and sub-types:
```js
categories = [upsc, ssc, banking, railway, campus_it, campus_mba, hr, quick]

subTypes = {
  upsc:       [full_mock, daf_based, current_affairs, optional, panel],
  campus_it:  [tcs_ninja, tcs_digital, infosys, wipro, amazon, google, microsoft, goldman],
  banking:    [sbi_po, ibps_po, rbi_grade_b],
  ssc:        [cgl, chsl, gd],
  railway:    [ntpc, group_d],
  campus_mba: [hr_round, case, finance],
  hr:         [general],
  quick:      [mixed],
}
```

### `Dashboard.jsx` — Analytics

- Greeting varies by time of day (morning/afternoon/evening)
- 4 stat cards: Total Sessions, Avg Score, Streak, Percentile
- Line chart: `comm` (clarity_score) and `tech` (technical_score) from last 10 sessions
- Radar chart: 6 dimensions from `stats.radar` object — keys with camelCase converted to space-separated labels
- Recent sessions table: last 5, with type label, score badge, duration, date, View Results link
- Renders `<OnboardingWizard />` — shows only if `!user.onboarding_completed && total_interviews === 0 && not localStorage dismissed`

### `Practice.jsx` — Question Bank

- Default filter: `category = "mine"` → maps to `user.exam_focus` (role-aware)
- Filters: Category (9 options), Difficulty (all/easy/medium/hard), Type (all/long_answer/situational/current_affairs/hr/technical)
- Each question card shows category badge, type badge, difficulty badge (color-coded), question text
- Bookmark icon (UI only — no backend bookmark API yet)
- "Practice This Answer" → opens modal with voice or text answer input → POST /practice/feedback

### `CurrentAffairs.jsx` — News + AI Questions

- Category tabs: Relevant, All, Economy, Polity, International, Environment, Science & Tech, Social, Defence, Sports
- "Relevant" tab filters by `EXAM_RELEVANCE[user.exam_focus]` mapping:
  ```js
  upsc:       ["Polity", "Economy", "International", "Environment", "Science & Tech", "Social"]
  banking:    ["Economy", "Polity"]
  ssc:        ["Polity", "Economy", "Social", "Sports"]
  railway:    ["Polity", "Social", "Economy"]
  campus_it:  ["Science & Tech", "Economy"]
  campus_mba: ["Economy", "International", "Polity"]
  ```
- Top 5 digest shown in gold-bordered card
- Click any news item → modal opens with summary + "Generate Interview Questions" button → POST /current-affairs/questions → returns 3 AI questions

### `Profile.jsx` — 4 Tabs

| Tab | Fields |
|---|---|
| Personal Info | Full Name, Email (read-only), Phone, State, College/Institution, LinkedIn, Bio (200 char), Target Year |
| Exam Settings | Primary Exam Goal, DAF Optional Subject, DAF Home State, DAF Hobbies, DAF Service Preference, Preferred Language, Difficulty Preference |
| Resume | Upload zone → POST /resume/parse — shows parsed skills grid if already uploaded |
| Achievements | Static display of interview count, streak, certificates (UI placeholder) |

### `Signup.jsx` — Registration

- Full-screen 2-column layout: left = branded hero with ParticleField + testimonial quote, right = form
- All 37 Indian states + UTs in dropdown (`STATES` array hardcoded)
- Exam focus select: UPSC, SSC, Banking, Railway, Campus IT, Campus MBA
- Password visibility toggle
- Calls `useAuth().signup()` → stores token → redirects to `/dashboard`

### `Login.jsx` — Sign In

- Same 2-column layout as Signup
- "Use Demo Account" button: pre-fills `demo@mitharva.ai` / `Demo@2026`
- Calls `useAuth().login()` → stores token → redirects to `/dashboard`

### `Subscription.jsx` — Plan Management

Actual plan limits enforced in both frontend and backend:

| Plan | Monthly Interviews | Price | Backend amount |
|---|---|---|---|
| Free | 2 | ₹0 | — |
| Basic | 10 | ₹199/month | `amounts["basic"] = 199` |
| Pro | 100 (displayed as "Unlimited") | ₹499/month | `amounts["pro"] = 499` |

Usage bar: `Math.min(100, (interviews_used_this_month / limit) * 100)%`

Payment simulation: 1.5-second `setTimeout` to simulate Razorpay processing → POST /subscription/mock-pay → refresh user → fetch billing history

### `OnboardingWizard.jsx` — First-Visit Modal

Show condition: `!user.onboarding_completed && !localStorage.getItem("mitharva_onboarding_${user.id}") && total_interviews === 0`

Step 1: Preparation stage — "Just starting out" / "1-2 years preparation" / "Final lap (this attempt)"

Step 2: Previous attempts — "First attempt" / "Second attempt" / "Third or more"

Step 3: Challenges (multi-select toggles) + Language preference
- Challenge options: Nervousness, Answer Structure, Language Barrier, Domain Knowledge, Current Affairs, Body Language
- Language: English, Hindi

On finish: POST /api/profile/onboarding → updateUser() → sets localStorage dismissed key → shows success toast

On skip/close: only sets localStorage key (does not call API)

### `RoleSwitcher.jsx` — Live Exam Focus Change

6 options with emoji icons:

```js
const EXAMS = [
  { k: "upsc",       label: "UPSC Civil Services", icon: "🏛️" },
  { k: "ssc",        label: "SSC",                  icon: "📋" },
  { k: "banking",    label: "Banking",               icon: "🏦" },
  { k: "railway",    label: "Railway",               icon: "🚂" },
  { k: "campus_it",  label: "Campus IT",             icon: "💻" },
  { k: "campus_mba", label: "Campus MBA",            icon: "🎓" },
];
```

On selection: PATCH /api/profile { exam_focus: k } → updateUser() → success toast → all content re-renders (Practice filters, Dashboard suggestions, Current Affairs relevance, Interview Setup category)

---

## 7. Design System & Theming

### Brand Colors

Defined as CSS variables in `index.css` and Tailwind config:

```css
/* Brand tokens */
--navy-deep:  #060B1C;   /* Tailwind: navy-deep */
--navy:       #0A1633;   /* Tailwind: navy */
--navy-mid:   #142048;   /* Tailwind: navy-mid */
--navy-light: #1E2C5E;   /* Tailwind: navy-light */
--gold:       #C69A3C;   /* Tailwind: gold (index.css) / #B8962E (tailwind.config) */
--gold-light: #DDB860;   /* Tailwind: gold-light */
--gold-bright:#F0CC6F;   /* Tailwind: gold-bright */
```

> Note: There are two gold values in the codebase — `#C69A3C` in CSS vars and `#B8962E` in Tailwind config. The Tailwind value (`#B8962E`) is used in most component inline styles. CSS var is used in legacy utility classes.

### Typography — 4 Font Families

| Font | CSS Class | Tailwind | Used For |
|---|---|---|---|
| Cormorant Garamond | `.font-display` | `font-display` | Page headings, scores, brand name |
| Outfit | `.font-body` | `font-body` | Body text (also the default `body` font) |
| JetBrains Mono | `.font-mono` | `font-mono` | Scores, timer, monospace numbers |
| Noto Sans Devanagari | `.font-deva` | `font-devanagari` | Sanskrit tagline, Hindi text |

All 4 fonts are loaded from Google Fonts via `@import` in `index.css`.

### CSS Utility Classes (defined in `index.css`)

```css
.gradient-gold-text      /* linear-gradient gold text with background-clip */
.gradient-gold-bg        /* linear-gradient gold background */
.gradient-hero           /* radial + linear dark navy hero background */
.glow-gold               /* box-shadow gold glow (large) */
.glow-gold-sm            /* box-shadow gold glow (small) */
.circuit-bg              /* grid pattern with subtle gold lines */
.glass-nav               /* backdrop-blur navbar with border */
.card-surface            /* white/dark card with border-radius 1rem */
.panel-surface           /* slightly darker panel surface */
.wave-bars               /* animated 4-bar waveform for speaking indicator */
.particle                /* animated floating gold dot */
.orb-idle/listening/processing/speaking   /* gold orb states */
```

### Tailwind Custom Keyframes

| Animation | Keyframe | Use |
|---|---|---|
| `pulse-gold` | 0→28px→0 box-shadow | Idle orb, panel avatar when speaking |
| `float` | translateY(0) ↔ translateY(-12px) | Floating elements |
| `drift` | translate(0,0)↔(20px,-30px) + opacity | Particles |
| `wave` | height 4px ↔ 22px | Wave bars animation |
| `fade-up` | opacity+translateY → visible | Page entrance animations |
| `shimmer` | backgroundPosition 200% | Loading shimmer effect |
| `accordion-down/up` | height 0 ↔ content-height | Accordion open/close |

### Dark vs Light Mode

Dark is the default. Light mode changes:
- Background: `#FAF6EC` (warm cream) vs `#060B1C` (deep navy)
- Cards: `#FFFFFF` vs `#0A1633`
- Text: deep navy vs warm white/cream
- Hero: cream gradient vs dark navy radial gradient
- Glass navbar: semi-transparent cream vs semi-transparent navy

---

## 8. Build & Dev Tooling

### CRACO Configuration (`craco.config.js`)

CRACO (Create React App Configuration Override) extends CRA without ejecting:

1. **Webpack alias**: `@/` → `src/` (enables `import api from "@/lib/api"` etc.)
2. **ESLint**: Adds `react-hooks/recommended` rules
3. **WatchOptions**: Ignores `node_modules`, `.git`, `build`, `dist`, `coverage`, `public` to reduce memory
4. **Health Check plugin** (optional): Activated only when `ENABLE_HEALTH_CHECK=true` env var is set
5. **Health Check plugin** (optional): Activated only when `ENABLE_HEALTH_CHECK=true` env var is set

### Webpack Health Check Plugin System

An optional monitoring layer for the dev server. Activated with `ENABLE_HEALTH_CHECK=true`.

**`webpack-health-plugin.js`** hooks into webpack compiler lifecycle:
- `compiler.hooks.compile` → sets state to "compiling", records start time
- `compiler.hooks.done` → sets state to "success"/"failed", records errors/warnings, calculates duration
- `compiler.hooks.failed` → captures fatal errors
- `compiler.hooks.invalid` → file change detected, back to "compiling"

**`health-endpoints.js`** exposes 6 Express endpoints on the webpack dev server:

| Endpoint | Response | Use Case |
|---|---|---|
| `GET /health` | Full JSON — state, uptime, webpack status, memory | Monitoring dashboards |
| `GET /health/simple` | Text: `OK` / `COMPILING` / `IDLE` / `ERROR` | Simple uptime checks |
| `GET /health/ready` | JSON `{ ready: bool, state }` | Kubernetes readiness probe |
| `GET /health/live` | JSON `{ alive: true, timestamp }` | Kubernetes liveness probe |
| `GET /health/errors` | JSON `{ errorCount, errors[], warnings[] }` | CI error reporting |
| `GET /health/stats` | JSON `{ totalCompiles, avgCompileTime, serverUptime }` | Performance monitoring |

### `jsconfig.json` — Path Aliases

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  }
}
```

Combined with CRACO's webpack alias, this enables both IDE autocomplete and runtime resolution of `@/` imports.

### `components.json` — shadcn/ui Configuration

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": false,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

All 40+ shadcn components use the `new-york` style with CSS variables for theming — which is why dark/light mode works without any JS re-rendering of components.

---

## 9. Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `MONGO_URL` | ✅ Yes | MongoDB connection string. `mongodb://localhost:27017` or MongoDB Atlas URI |
| `DB_NAME` | ✅ Yes | Database name. Example: `mitharva_ai` |
| `JWT_SECRET` | ✅ Yes | JWT signing secret. **Must be changed in production.** Minimum 32 characters recommended |
| `LLM_API_KEY` | ⚠️ AI features | Gemini API key (Google AI Studio). Without it, all AI responses return mock data |
| `GEMINI_MODEL` | Optional | Gemini model id used by `call_gemini`. Defaults to `gemini-2.0-flash`; this project's free-tier key uses `gemini-flash-lite-latest` (other Flash variants hit the free-tier rate limit) |
| `ELEVENLABS_API_KEY` | ⚠️ Voice output | ElevenLabs API key for `POST /api/voice/tts` (interviewer's spoken voice). Without it, the endpoint returns a clean error and the frontend falls back to the browser's built-in `speechSynthesis` |
| `ELEVENLABS_VOICE_ID` | Optional | ElevenLabs voice id. Defaults to the "Adam" multilingual voice (`pNInz6obpgDQGcFmaJgB`) |
| `CORS_ORIGINS` | Optional | Comma-separated allowed origins. Defaults to `*` if not set. Example: `http://localhost:3000,https://yourapp.com` |

### Frontend (`frontend/.env`)

| Variable | Required | Description |
|---|---|---|
| `REACT_APP_BACKEND_URL` | ✅ Yes | Backend base URL **without** trailing slash. Example: `http://localhost:8001`. Used in `lib/api.js` and directly in `InterviewRoom.jsx` for Whisper STT fetch |

> **Important**: The frontend uses `REACT_APP_BACKEND_URL` directly in the InterviewRoom for the Whisper STT multipart upload (uses `fetch()` instead of Axios because it's `multipart/form-data`).

### Without `LLM_API_KEY` (Mock Mode)

All interview turns return this deterministic mock response:
```json
{
  "nextQuestion": "Thank you for that answer. Could you elaborate on a specific example where you demonstrated leadership in a challenging situation?",
  "speakerName": "Shri R.K. Sharma",
  "evaluation": {
    "technicalScore": 7.5, "clarityScore": 7.8, "structureScore": 7.4,
    "confidenceEstimate": 7.0, "overallScore": 7.4,
    "keyStrengths": ["Clear articulation", "Good factual accuracy"],
    "improvementAreas": ["Add more concrete examples"],
    "liveTip": "Try the STAR method: Situation, Task, Action, Result"
  },
  "isInterviewComplete": false
}
```
The Whisper STT endpoint (`/api/voice/stt`) returns HTTP 500 without the key.

---

## 10. Local Setup — Step by Step

### Prerequisites

| Tool | Minimum Version | Check Command |
|---|---|---|
| Python | 3.11+ | `python --version` |
| pip | latest | `pip --version` |
| Node.js | 18+ | `node --version` |
| Yarn | 1.22+ | `yarn --version` |
| MongoDB | 6.0+ (local) or Atlas | — |
| Git | any | `git --version` |

---

### Step 1 — Clone

```bash
git clone https://github.com/arpitms404/Mitharava-AI.git
cd Mitharava-AI
```

---

### Step 2 — Backend Setup

#### 2a. Create virtual environment and activate

```bash
cd backend
python -m venv venv

# macOS / Linux:
source venv/bin/activate

# Windows Command Prompt:
venv\Scripts\activate.bat

# Windows PowerShell:
venv\Scripts\Activate.ps1
```

#### 2b. Install dependencies

```bash
pip install -r requirements.txt
```

All versions are pinned. Key packages include FastAPI, Motor, bcrypt, PyJWT, pypdf, reportlab, openai, and google-generativeai.

#### 2c. Create environment file

Create `backend/.env` with the following content:

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=mitharva_ai
JWT_SECRET=replace-this-with-a-32-char-secret-key
LLM_API_KEY=your-llm-api-key-here
CORS_ORIGINS=http://localhost:3000
```

#### 2d. Start the backend

```bash
# From backend/ directory, with venv active:
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```

**What happens on first start:**
- FastAPI starts on `http://localhost:8001`
- `on_startup` event fires → `seed_database()` runs
- 30 questions, 10 current affairs, and demo user are inserted (only if collections are empty)
- Auto-generated interactive docs available at: `http://localhost:8001/docs` (Swagger UI)
- Alternative docs: `http://localhost:8001/redoc`

**Verify it's running:**
```bash
curl http://localhost:8001/api/health
# Expected: {"status":"ok"}

curl http://localhost:8001/api/
# Expected: {"message":"Mitharva AI API","version":"1.0.0"}
```

---

### Step 3 — Frontend Setup

Open a new terminal window/tab:

```bash
cd frontend
yarn install
```

#### 3a. Create frontend environment file

```bash
# Create frontend/.env:
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env
```

#### 3b. Start the development server

```bash
yarn start
```

The app opens automatically at `http://localhost:3000`.

---

### Step 4 — Verify the Full Stack

1. **Landing page**: `http://localhost:3000` → navy dark theme, gold logo, particle animation
2. **Login**: `http://localhost:3000/auth/login` → click "Use Demo Account" → click Login
3. **Dashboard**: Should show 4 stat cards, line chart, radar chart, 12 recent sessions
4. **New Interview**: Click "New Interview" → 5-step setup wizard → launch interview
5. **API docs**: `http://localhost:8001/docs` → interactive Swagger UI for all 19 endpoints

---

## 11. API Reference

All routes are under the `/api` prefix. Protected routes require:
```
Authorization: Bearer <JWT token>
```

### Health

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/` | ❌ | `{ "message": "Mitharva AI API", "version": "1.0.0" }` |
| GET | `/api/health` | ❌ | `{ "status": "ok" }` |

---

### Authentication

#### `POST /api/auth/signup`

```json
// Request body
{
  "full_name": "Priya Sharma",
  "email": "priya@example.com",
  "password": "SecurePass@123",
  "phone": "+919876543210",       // optional
  "exam_focus": "upsc",           // optional, defaults to "upsc"
  "state": "Rajasthan",           // optional
  "college": "NIT Jaipur"         // optional
}

// Response 200
{
  "token": "eyJhbGci...",
  "user": {
    "id": "uuid",
    "full_name": "Priya Sharma",
    "email": "priya@example.com",
    "exam_focus": "upsc",
    "plan": "free",
    "total_interviews": 0,
    "interviews_used_this_month": 0,
    "streak_days": 0,
    "daf_optional_subject": "",
    "daf_home_state": "Rajasthan",
    ...
  }
}
// Error 400: Email already registered
```

#### `POST /api/auth/login`

```json
// Request
{ "email": "demo@mitharva.ai", "password": "Demo@2026" }

// Response 200: same shape as signup
// Error 401: Invalid email or password
```

#### `GET /api/auth/me`

Returns current user profile. No body. Requires JWT.

---

### Profile

#### `PATCH /api/profile`

Send any subset of updatable fields:

```json
// Request (all optional)
{
  "full_name": "New Name",
  "phone": "+91...",
  "state": "Maharashtra",
  "college": "IIT Bombay",
  "bio": "UPSC aspirant...",
  "target_year": 2027,
  "preferred_language": "hindi",
  "difficulty_preference": "hard",
  "exam_focus": "banking",
  "daf_optional_subject": "Geography",
  "daf_home_state": "Maharashtra",
  "daf_hobbies": "Chess, Reading",
  "daf_service_preference": "IPS",
  "linkedin": "linkedin.com/in/yourname"
}

// Response 200: Full updated user object
```

#### `POST /api/profile/onboarding`

```json
// Request
{
  "preparation_stage": "Final lap (this attempt)",
  "previous_attempts": "Second attempt",
  "challenges": ["Nervousness", "Current Affairs"],
  "preferred_language": "hindi"
}

// Response 200: Full updated user object with onboarding_completed: true
```

---

### Interview Sessions

#### `POST /api/sessions` — Create Session

```json
// Request
{
  "session_type": "upsc",
  "sub_type": "full_mock",
  "duration_minutes": 30,
  "difficulty": "medium",
  "language": "english",
  "mode": "voice_camera",
  "company": ""
}

// Response 200: Full session object with status: "active"
```

Session types: `upsc`, `ssc`, `banking`, `railway`, `campus_it`, `campus_mba`, `hr`, `quick`

Modes: `voice_camera`, `voice`, `text`

Languages: `english`, `hindi`

#### `GET /api/sessions` — List Sessions

Returns array sorted by `created_at` descending. Max 200 results.

#### `GET /api/sessions/{session_id}` — Get One Session

#### `POST /api/sessions/turn` — Submit Answer, Get Next Question

```json
// Request
{
  "session_id": "uuid",
  "user_message": "I believe cooperative federalism works best when...",
  "question_index": 2
}

// Response 200
{
  "raw": "{...json string from LLM...}",
  "parsed": {
    "nextQuestion": "Could you cite a specific example?",
    "speakerName": "Shri R.K. Sharma",
    "evaluation": {
      "technicalScore": 8.2,
      "clarityScore": 7.5,
      "structureScore": 7.8,
      "confidenceEstimate": 7.0,
      "overallScore": 7.6,
      "keyStrengths": ["Good conceptual clarity"],
      "improvementAreas": ["Quantify outcomes"],
      "liveTip": "Add 1-2 specific policy examples"
    },
    "isInterviewComplete": false
  }
}
```

#### `POST /api/sessions/complete` — End Interview

```json
// Request
{
  "session_id": "uuid",
  "transcript": [
    { "role": "assistant", "speaker": "Shri R.K. Sharma", "text": "Tell us about yourself...", "evaluation": null },
    { "role": "user", "text": "Good morning, I am Priya...", "evaluation": null },
    { "role": "assistant", "speaker": "Shri R.K. Sharma", "text": "...", "evaluation": { ... } }
  ],
  "duration_seconds": 1680,
  "camera_used": true
}

// Response 200: Completed session with aggregated scores
{
  "status": "completed",
  "overall_score": 7.8,
  "technical_score": 8.1,
  "clarity_score": 7.5,
  ...
}
```

#### `GET /api/sessions/{session_id}/report.pdf`

Returns streaming PDF binary with `Content-Disposition: attachment`. Download link used directly in `InterviewResults.jsx` via `fetch()` with JWT header.

---

### Question Bank

#### `GET /api/questions`

Query parameters (all optional):
- `category`: `upsc`, `banking`, `campus_it`, `ssc`, `campus_mba` (or omit/`all` for all)
- `difficulty`: `easy`, `medium`, `hard`
- `type`: `long_answer`, `situational`, `current_affairs`, `hr`, `technical`

Returns array of up to 500 questions.

---

### Practice

#### `POST /api/practice/feedback`

```json
// Request
{
  "question": "What is cooperative federalism?",
  "answer": "Cooperative federalism refers to...",
  "exam_type": "upsc"
}

// Response 200
{
  "score": 7.5,
  "strengths": ["Clear structure", "Good examples"],
  "improvements": ["Add quantifiable outcomes"],
  "modelAnswerApproach": "Open with definition, support with 2-3 examples...",
  "keyPoints": ["Use STAR method", "Cite recent schemes"]
}
```

---

### Current Affairs

#### `GET /api/current-affairs`

Optional query param: `category` (Economy, Polity, Science & Tech, Social, Defence, International)

Returns array sorted by `published_date` descending. Max 100.

#### `POST /api/current-affairs/questions`

```json
// Request
{
  "news_title": "India Launches First Indigenous 50-Qubit Quantum Computer",
  "news_summary": "IIT Delhi and DRDO jointly unveiled..."
}

// Response 200: Array of 3 questions
[
  { "question": "What is quantum computing and its significance for India?", "difficulty": "medium", "hint": "Consider strategic, scientific, economic angles" },
  { "question": "What policy reforms would strengthen India's quantum ecosystem?", "difficulty": "hard", "hint": "Multi-stakeholder framework" },
  { "question": "How does this impact India's technological sovereignty?", "difficulty": "easy", "hint": "Ground level perspective" }
]
```

---

### Voice & File APIs

#### `POST /api/voice/stt`

Multipart form upload. Fields:
- `file`: Audio blob (webm, mp4, wav — max 25MB)
- `language`: `english`→`en`, `hindi`→`hi`, `hinglish`→`hi`, `tamil`→`ta`, `bengali`→`bn`, `marathi`→`mr`

```json
// Response 200
{ "text": "transcribed text here" }
// Error 500 (no LLM_API_KEY): "LLM key not configured"
```

#### `POST /api/resume/parse`

Multipart form upload. Field: `file` (PDF, max 5MB)

```json
// Response 200
{
  "filename": "my_resume.pdf",
  "text_length": 4521,
  "parsed": {
    "name": "Priya Sharma",
    "email": "priya@example.com",
    "phone": "+91...",
    "skills": ["Python", "Machine Learning", "Data Analysis"],
    "education": [{ "degree": "B.Tech CSE", "institution": "NIT Jaipur", "year": "2024" }],
    "experience": [{ "title": "SDE Intern", "company": "Infosys", "duration": "6 months", "description": "..." }],
    "projects": [{ "name": "AI Chatbot", "description": "...", "tech": ["Python", "FastAPI"] }],
    "achievements": ["Top 5% in GATE 2024"]
  }
}
```

---

### Subscription

#### `POST /api/subscription/mock-pay`

```json
// Request
{ "plan": "basic" }  // or "pro"

// Response 200
{ "success": true, "plan": "basic", "amount": 199 }
// Error 400: Invalid plan
```

#### `GET /api/subscription/history`

Returns billing history array sorted newest first. Max 50 records.

---

### Dashboard

#### `GET /api/dashboard/stats`

```json
// Response 200
{
  "total_sessions": 12,
  "avg_score": 7.45,
  "streak": 5,
  "percentile": 77,
  "chart_data": [
    { "date": "2026-04-01", "comm": 7.2, "tech": 8.1 },
    ...
  ],
  "radar": {
    "Technical": 7.8,
    "Communication": 7.2,
    "Confidence": 6.8,
    "Structure": 7.4,
    "CurrentAffairs": 7.1,
    "Domain": 7.6
  },
  "recent": [ ...last 5 sessions... ]
}
```

---

## 12. Database Schema

MongoDB with 5 collections. Motor (async) driver used throughout.

### `users` collection

```js
{
  id: String,                       // UUID v4 — primary key (not _id)
  full_name: String,
  email: String,                    // unique
  phone: String,
  password: String,                 // bcrypt hash
  exam_focus: String,               // "upsc" | "ssc" | "banking" | "railway" | "campus_it" | "campus_mba"
  state: String,                    // Indian state
  college: String,
  preferred_language: String,       // "english" | "hindi"
  difficulty_preference: String,    // "easy" | "medium" | "hard"
  plan: String,                     // "free" | "basic" | "pro"
  interviews_used_this_month: Number,
  total_interviews: Number,
  streak_days: Number,
  bio: String,                      // max 200 chars
  linkedin: String,
  target_year: Number,              // e.g. 2026
  daf_optional_subject: String,     // UPSC: "Geography", "History", etc.
  daf_home_state: String,
  daf_hobbies: String,
  daf_service_preference: String,   // "IAS" | "IPS" | "IFS" etc.
  resume_filename: String,
  resume_parsed_data: Object,       // Structured JSON from /resume/parse
  resume_uploaded_at: String,
  onboarding_completed: Boolean,
  onboarding_completed_at: String,
  preparation_stage: String,
  previous_attempts: String,
  challenges: Array,
  created_at: String                // ISO 8601 datetime
}
```

### `sessions` collection

```js
{
  id: String,                         // UUID v4
  user_id: String,                    // Foreign key → users.id
  session_type: String,               // "upsc" | "banking" | "campus_it" | "ssc" | "campus_mba" | "hr" | "quick" | "railway"
  sub_type: String,                   // e.g. "full_mock", "tcs_digital", "sbi_po"
  duration_minutes: Number,
  duration_seconds: Number,           // Set on complete
  difficulty: String,
  language: String,
  mode: String,                       // "voice_camera" | "voice" | "text"
  company: String,                    // For campus_it company-specific prep
  status: String,                     // "active" | "completed"
  transcript: Array,                  // [{role, speaker, text, evaluation, ts}]
  overall_score: Number | null,       // 0-10, aggregated on complete
  technical_score: Number | null,
  clarity_score: Number | null,
  structure_score: Number | null,
  confidence_score: Number | null,
  current_affairs_score: Number | null, // Derived: min(10, overall + 0.2)
  domain_score: Number | null,          // Derived: min(10, overall + 0.3)
  questions_count: Number,
  camera_used: Boolean,
  created_at: String,
  completed_at: String | null
}
```

### `questions` collection

```js
{
  id: String,                       // UUID v4
  category: String,                 // "upsc" | "banking" | "campus_it" | "ssc" | "campus_mba"
  difficulty: String,               // "easy" | "medium" | "hard"
  type: String,                     // "hr" | "situational" | "long_answer" | "current_affairs" | "technical"
  question_text: String,
  is_active: Boolean,
  created_at: String
}
```

### `current_affairs` collection

```js
{
  id: String,
  title: String,
  summary: String,
  source: String,                   // "RBI", "PIB", "ISRO", "MEA", "Supreme Court", etc.
  category: String,                 // "Economy" | "Polity" | "Science & Tech" | "Social" | "Defence" | "International"
  published_date: String,           // "YYYY-MM-DD"
  is_active: Boolean,
  created_at: String
}
```

### `billing_history` collection

```js
{
  id: String,
  user_id: String,                  // Foreign key → users.id
  amount: Number,                   // 199 or 499 (INR)
  plan: String,                     // "basic" | "pro"
  razorpay_payment_id: String,      // "mock_pay_<12-hex>" in development
  status: String,                   // "paid"
  created_at: String
}
```

---

## 13. Authentication Flow

```
SIGNUP:
─────────────────────────────────────────────────────────────────────────
Browser POST /api/auth/signup
  → FastAPI SignupIn validation (Pydantic + EmailStr)
  → db.users.find_one(email) → 400 if duplicate
  → user_id = uuid4()
  → password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
  → db.users.insert_one({ id, email, hashed_password, exam_focus, plan:"free", ... })
  → token = jwt.encode({ sub: user_id, exp: now+30days, iat: now }, JWT_SECRET, HS256)
  → return { token, user (no password, no _id) }

BROWSER:
  → localStorage.setItem("mitharva_token", token)
  → AuthContext.setUser(user)
  → Navigate to /dashboard

LOGIN:
─────────────────────────────────────────────────────────────────────────
Browser POST /api/auth/login
  → db.users.find_one(email) → 401 if not found
  → bcrypt.checkpw(password.encode(), stored_hash.encode()) → 401 if false
  → create_token(user_id) → same as above
  → return { token, user }

PROTECTED REQUEST:
─────────────────────────────────────────────────────────────────────────
Axios interceptor reads localStorage "mitharva_token"
  → Adds "Authorization: Bearer <token>" header

FastAPI Depends(get_current_user):
  → security = HTTPBearer(auto_error=False)
  → If no creds → 401 "Not authenticated"
  → jwt.decode(token, JWT_SECRET, ["HS256"]) → 401 "Invalid token" on failure
  → user_id = payload["sub"]
  → db.users.find_one({ id: user_id }, { _id:0, password:0 }) → 401 if not found
  → Inject user dict into route handler

SESSION EXPIRY:
─────────────────────────────────────────────────────────────────────────
Axios response interceptor:
  → On 401 response → localStorage.removeItem("mitharva_token")
  → AuthContext soft-logout on next render
```

---

## 14. Interview Session Lifecycle

```
SETUP (/interview/setup)
─────────────────────────────────────────────────────────────────────────
User selects: category → sub-type → settings (duration/difficulty/language/mode)
Optional: Upload resume → POST /api/resume/parse → parsed data saved to profile
Click "Begin Interview" → POST /api/sessions → returns { id, status:"active", ... }
Navigate to /interview/room/:id

LIVE ROOM (/interview/room/:id)
─────────────────────────────────────────────────────────────────────────
Load session: GET /api/sessions/:id

Camera/Mic init:
  mode === "voice_camera" → getUserMedia({ video:true, audio:true })
  mode === "voice"        → getUserMedia({ video:false, audio:true })
  mode === "text"         → setTextMode(true), no media request

Opening line:
  After 1s delay → add { role:"assistant", speaker:"Shri R.K. Sharma", text: DEMO_OPENING } to transcript
  → speak(DEMO_OPENING) → browser SpeechSynthesis
  → orbState → "speaking" → on end → "idle"

Per-turn loop:
  [Voice mode]
    User taps orb → orbState = "listening"
    
    [Whisper mode — default]
      MediaRecorder.start() → audio chunks collected
      User taps orb again → MediaRecorder.stop()
      blob → POST /api/voice/stt (multipart, with JWT)
      → Whisper transcription → text
      → submitAnswer(text)
    
    [Browser STT mode — fallback]  
      SpeechRecognition.start() → interim results shown live
      Recognition ends → submitAnswer(finalText)
  
  submitAnswer(text):
    orbState = "processing"
    Add user message to transcript
    POST /api/sessions/turn { session_id, user_message, question_index }
    → Backend: build system prompt → call_gemini() → Gemini 3 Flash
    → Response parsed: { nextQuestion, speakerName, evaluation, isInterviewComplete }
    Rotate currentSpeaker (0→1→2→0)
    setLatestEval(evaluation) → updates live analytics sidebar
    Add AI message to transcript
    speak(nextQuestion) → browser SpeechSynthesis
    orbState → "speaking" → on end → "idle"
    
    If isInterviewComplete || qIndex >= 11:
      setTimeout(endInterview, 5000)

End Interview:
  User clicks "End" → endConfirm modal
  Confirm → POST /api/sessions/complete { transcript, duration_seconds, camera_used }
  → Backend aggregates scores → sets status:"completed"
  Navigate to /interview/results/:id

RESULTS (/interview/results/:id)
─────────────────────────────────────────────────────────────────────────
GET /api/sessions/:id → load completed session
Animated score ring: setInterval increments animScore from 0 → overall_score (30 steps)
Radar chart: 6 dimensions from session object
Transcript tab: all messages with per-answer evaluation
Action plan: hardcoded 3-week plan (Week 1 Confidence, Week 2 Filler Words, Week 3 Current Affairs)
Share: navigator.clipboard.writeText(window.location.href)
Download PDF: fetch(`${API}/sessions/${id}/report.pdf`) with JWT → blob → auto-download link
```

---

## 15. AI & LLM Architecture

### Gemini 3 Flash (Primary LLM)

Used for: interview question generation, follow-up questioning, answer evaluation, practice feedback, current affairs question generation, resume parsing.

```python
from emergentintegrations.llm.chat import LlmChat, UserMessage

chat = LlmChat(
    api_key=LLM_API_KEY,
    session_id=session_id,         # Stateful — Gemini maintains conversation history
    system_message=system_prompt,  # Persona + JSON format rules
).with_model("gemini", "gemini-3-flash-preview")

msg = UserMessage(text=user_message)
response = await chat.send_message(msg)  # Returns string
```

The `session_id` is critical — it means each interview session keeps its own conversation history inside Gemini. The backend does not need to send the full transcript on every turn; Gemini remembers.

### JSON Output Contract

Every interview turn response must match exactly:
```json
{
  "nextQuestion": "string — the next question to ask",
  "speakerName": "string — which panelist is asking (e.g. Shri R.K. Sharma)",
  "evaluation": {
    "technicalScore": 0.0,       // 0-10 decimal
    "clarityScore": 0.0,
    "structureScore": 0.0,
    "confidenceEstimate": 0.0,
    "overallScore": 0.0,
    "keyStrengths": ["string"],
    "improvementAreas": ["string"],
    "liveTip": "string — actionable 1-line tip"
  },
  "isInterviewComplete": false   // true after 10-12 questions
}
```

### Practice Feedback Contract

```json
// Prompt: "Return ONLY valid JSON: {score:0-10, strengths:[], improvements:[], modelAnswerApproach:'', keyPoints:[]}"
{
  "score": 7.5,
  "strengths": ["Clear structure", "Good examples"],
  "improvements": ["Add quantifiable outcomes"],
  "modelAnswerApproach": "Open with a clear thesis...",
  "keyPoints": ["STAR method", "Recent policy examples"]
}
```

### Current Affairs Question Generation Contract

```json
// Prompt: "Return ONLY valid JSON array: [{question:'', difficulty:'easy|medium|hard', hint:''}]"
[
  { "question": "...", "difficulty": "medium", "hint": "..." },
  { "question": "...", "difficulty": "hard",   "hint": "..." },
  { "question": "...", "difficulty": "easy",   "hint": "..." }
]
```

### Resume Parsing Contract

```json
// Prompt: "Parse this resume into clean JSON with exact keys: name, email, phone, skills[], education[], experience[], projects[], achievements[]"
```

---

## 16. Voice & Speech Pipeline

### Primary: OpenAI Whisper (Server-Side STT)

```
Browser → MediaRecorder.start()
       → User speaks
       → orb tapped or auto-stop
       → MediaRecorder.stop()
       → ondataavailable chunks collected
       → Blob created (audio/webm;codecs=opus preferred, audio/webm fallback, audio/mp4 for Safari)
       → If blob.size < 1000 bytes → discard (silence/noise)
       → FormData: { file: blob("audio.webm"), language: session.language }
       → fetch(`${REACT_APP_BACKEND_URL}/api/voice/stt`, { method:POST, headers:{Authorization:Bearer...}, body:fd })
       → Backend: OpenAISpeechToText (Whisper-1)
       → Whisper-1 model → JSON response { text: "transcribed text" }
       → Frontend: submitAnswer(data.text.trim())
```

Language mapping in backend:
```python
lang_map = {
  "english":  "en",
  "hindi":    "hi",
  "hinglish": "hi",   # Hindi treated as target
  "tamil":    "ta",
  "bengali":  "bn",
  "marathi":  "mr"
}
```

### Fallback: Browser Web Speech API (Client-Side STT)

Activated when user clicks "Browser STT" toggle (`whisperMode = false`):

```js
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const r = new SR();
r.continuous = false;
r.interimResults = true;
r.lang = session.language === "hindi" ? "hi-IN" : "en-IN";
```

Live interim results shown in transcript as user speaks (animated pulse border).

### Text-to-Speech (AI Question Delivery)

All AI questions are spoken aloud using the browser's `SpeechSynthesis` API:

```js
const speak = (text) => {
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.95;  // slightly slower than normal
  u.pitch = 0.9;  // slightly deeper voice

  // Voice preference order:
  const voices = window.speechSynthesis.getVoices();
  const voice = 
    voices.find(v => /(en-IN|hi-IN)/i.test(v.lang))   ||  // Indian voice
    voices.find(v => /Google.*UK English Male|Daniel/i.test(v.name)) ||  // UK English
    voices[0];  // any available voice

  if (voice) u.voice = voice;
  u.onend = () => setOrbState("idle");
  window.speechSynthesis.speak(u);
};
```

---

## 17. Subscription & Billing

### Plan Details

| Plan | Monthly Limit | Price | Backend `amounts` |
|---|---|---|---|
| `free` | 2 interviews | ₹0 | not payable |
| `basic` | 10 interviews | ₹199/month | `199` |
| `pro` | 100 interviews (shown as "Unlimited") | ₹499/month | `499` |

### Plan Features (from Pricing page)

| Feature | Free | Basic | Pro |
|---|---|---|---|
| Interviews per month | 2 total | 10/month | Unlimited |
| Mode | Text only | Voice AI | Camera + body language AI |
| Resume-based questions | ❌ | ✅ | ✅ |
| PDF reports | ❌ | ✅ | ✅ |
| Hindi support | ❌ | ✅ | ✅ |
| Panel mode (3 AI) | ❌ | ❌ | ✅ |
| Priority support | ❌ | ❌ | ✅ |
| Advanced analytics | ❌ | ❌ | ✅ |

### Mock Payment Flow

```
Subscription page → user clicks "Upgrade to Pro"
  → upgrade("pro") called
  → setPaying(true)
  → setTimeout(1500ms) — simulates payment processing UI
  → POST /api/subscription/mock-pay { plan: "pro" }
  → Backend:
      amounts = { basic: 199, pro: 499 }
      Update users.plan = "pro", interviews_used_this_month = 0
      Insert billing_history: { id, user_id, amount:499, plan:"pro", razorpay_payment_id:"mock_pay_<hex>", status:"paid" }
  → Frontend: await refresh() → refetch /auth/me → update user state
  → Refetch billing history
  → Toast: "🎉 Welcome to PRO plan!"
```

Real Razorpay integration is planned (the `razorpay_payment_id` field already exists in the schema).

---

## 18. Testing

### Test Infrastructure

Tests use the `requests` library against a running backend instance. The backend URL is read from:
1. `REACT_APP_BACKEND_URL` environment variable
2. Fallback: reads `frontend/.env` file at `/app/frontend/.env`

### Running Tests

```bash
cd backend

# Activate virtual environment first
source venv/bin/activate  # macOS/Linux

# Install test dependencies (already in requirements.txt)
pip install pytest requests

# Run all tests with verbose output
pytest tests/ -v

# Run specific file
pytest tests/test_mitharva_backend.py -v
pytest tests/test_deferred_endpoints.py -v

# Run with JUnit XML output (CI/CD)
pytest tests/ --junit-xml=../test_reports/pytest/results.xml -v
```

The backend must be running and seeded with demo data before running tests.

### `test_mitharva_backend.py` — 31 Core Tests

| Test Class | Tests | What is tested |
|---|---|---|
| `TestHealth` | 2 | `/health` status ok, `/` API message |
| `TestAuth` | 5 | Demo login, wrong password, signup, duplicate email, GET /me |
| `TestProfile` | 2 | PATCH profile fields, onboarding endpoint |
| `TestSessions` | 7 | Create session, list, get, turn (mock LLM), complete, score aggregation |
| `TestQuestions` | 3 | List all, filter by category, filter by difficulty |
| `TestPractice` | 2 | Submit answer, feedback structure |
| `TestCurrentAffairs` | 3 | List all, filter by category, generate questions from news |
| `TestSubscription` | 3 | Mock pay basic, mock pay pro, billing history |
| `TestDashboard` | 2 | Stats response structure, radar keys |
| `TestSeedData` | 2 | Questions count ≥ 30, current affairs count ≥ 10 |

### `test_deferred_endpoints.py` — 13 Additional Tests

| Test | What is tested |
|---|---|
| Voice STT no key | Returns 500 when LLM_API_KEY not set |
| Voice STT silent WAV | Tests with generated 1-second silent WAV (16kHz mono) |
| Resume parse minimal PDF | Tests with reportlab-generated PDF |
| Onboarding save | POST /profile/onboarding sets all fields correctly |
| PDF report generation | GET /sessions/:id/report.pdf returns PDF content-type |
| PDF report structure | Verifies PDF binary header `%PDF` |
| + regression coverage | Re-runs key core tests to confirm no regressions |

### Test Report Files

- `test_reports/iteration_1.json` — Snapshot from initial build
- `test_reports/iteration_2.json` — Snapshot after deferred endpoints
- `test_reports/pytest/pytest_results.xml` — JUnit XML for CI integration
- `test_reports/pytest/deferred_results.xml` — JUnit XML for deferred tests
- `test_result.md` — Multi-agent testing protocol with task status tracking (YAML format)

### All `data-testid` Attributes

Every interactive element has a `data-testid` for automated UI testing:

```
brand-logo              navbar-logo-link        nav-home, nav-about, nav-pricing
nav-login               nav-start-free          nav-dashboard-btn
nav-mobile-toggle       public-navbar           public-footer
hero-start-free-btn     bottom-cta-start        enterprise-contact
pricing-toggle-monthly  pricing-toggle-annual   pricing-view-all
pricing-page-free       pricing-page-basic      pricing-page-pro (Pricing page)
signup-submit-btn       signup-exam             signup-state
login-submit-btn        login-email             login-password
login-demo-fill         login-signup-link
dashboard-sidebar       dashboard-main          dash-new-interview-btn
side-dashboard          side-new-interview      side-practice
side-current-affairs    side-profile            side-subscription
side-logout             role-switcher           role-opt-{k}
theme-toggle
setup-cat-{k}           stepper-{1-5}           setup-next
setup-back              setup-resume-zone       setup-resume-skip
setup-begin
interview-room          voice-orb               room-timer
room-end-btn            room-pause              room-mute
switch-text             toggle-whisper          text-input
text-submit             transcript-area         perm-allow
perm-deny               end-confirm             end-cancel
results-share           results-download        results-retry
results-retry-bottom
onboarding-modal        onboarding-close        onb-step-{1-3}
onb-next                onb-back                onb-finish
practice-{id}           practice-answer         practice-voice
practice-submit         practice-close          bookmark-{id}
filter-cat-{v}          filter-diff-{v}         filter-type-{v}
news-generate-top       news-modal-close
profile-tab-{k}         prof-name               prof-email
prof-phone              prof-state              prof-college
prof-linkedin           prof-bio                prof-year
prof-save               prof-daf-opt            prof-save-exam
sub-upgrade-top
```

---

## 19. Seed Data & Demo Credentials

### Demo Account

| Field | Value |
|---|---|
| Email | `demo@mitharva.ai` |
| Password | `Demo@2026` |
| Name | Rahul Kumar |
| Exam Focus | UPSC |
| State | Uttar Pradesh |
| College | NIT Allahabad |
| Plan | Basic |
| DAF Optional Subject | Geography |
| DAF Hobbies | Cricket, Reading, Social Work |
| DAF Service Preference | IAS |
| Total Interviews | 47 (profile counter) |
| Seeded Sessions | 12 completed sessions |

### Pre-seeded Session History (12 Sessions)

The demo user has 12 sessions spread over 45 days, covering all exam types:

| Session Type | Sub-type | Score | Duration | Camera |
|---|---|---|---|---|
| UPSC | full_mock | 8.1 | 28 min | Yes |
| Campus IT | tcs_digital | 7.9 | 22 min | No |
| Banking | sbi_po | 7.5 | 19 min | Yes |
| UPSC | current_affairs | 7.2 | 15 min | No |
| SSC | cgl_panel | 7.0 | 31 min | No |
| Campus IT | amazon_sde | 7.8 | 26 min | Yes |
| UPSC | daf_based | 7.4 | 20 min | Yes |
| Banking | rbi_grade_b | 6.8 | 18 min | No |
| Campus IT | infosys | 7.6 | 24 min | No |
| UPSC | full_mock | 6.5 | 29 min | No |
| SSC | chsl | 6.9 | 16 min | No |
| Campus MBA | hr_round | 7.3 | 22 min | No |

---

## 20. Deployment Notes

### Environment Image

The project requires Python 3.11+ and Node 18+ with the standard dependencies installed via `pip install -r requirements.txt` and `yarn install`.

### Production Checklist

Before deploying to production, ensure:

1. **Change JWT_SECRET** — The default `'change-me'` is insecure. Use at minimum 32 random characters.

2. **Set CORS_ORIGINS explicitly** — Do not leave as `*` in production:
   ```
   CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
   ```

3. **Use MongoDB Atlas or secured MongoDB** — Never expose a local MongoDB without auth in production.

4. **Set LLM_API_KEY** — Without it, all AI features return mock responses.

5. **Frontend build for production**:
   ```bash
   cd frontend
   REACT_APP_BACKEND_URL=https://your-api-domain.com yarn build
   ```
   Serves the `build/` directory via nginx or any static host.

6. **Backend in production**:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8001 --workers 4
   ```
   For multiple workers, ensure MongoDB connection handles concurrent clients (Motor is async-safe).

### `.gitignore` — What is Excluded

Key excluded items: `.env` and all variants, `node_modules/`, `venv/`, `.venv/`, `build/`, `dist/`, `__pycache__/`, `*.pyc`, `*.pack` (large binary files), `*.zip`, `*.tar.gz`, `memory/test_credentials.md`

---

## 21. Roadmap

### ✅ Completed (as of May 2026)

**Iteration 1 — Core Platform**
- 19 REST API endpoints with full JWT auth
- 13-page React SPA with all core flows
- Live AI interview room with gold orb, 3-panel, camera feed
- Gemini 3 Flash integration for interview simulation
- Dark/light theme with navy + gold brand system
- 30 seeded questions + 10 current affairs + demo user
- 31/31 backend tests passing

**Iteration 2 — Feature Expansion**
- OpenAI Whisper server-side STT (POST /api/voice/stt)
- Resume PDF parsing + skill chips in setup (POST /api/resume/parse)
- 3-step onboarding wizard (POST /api/profile/onboarding)
- PDF report download with ReportLab (GET /api/sessions/:id/report.pdf)
- 44/44 tests passing

**Iteration 3 — Branding & UX**
- Real logo PNG integration (navy + gold palette matched)
- Edge-to-edge layout (removed all max-width containers)
- Role-based content filtering across all pages
- RoleSwitcher widget with live content re-render
- 6 Railway option in exam types

**Iteration 4 — Phase 1 hardening (July 2026)**
- Replaced the dead `emergentintegrations` import with a direct `google-generativeai` call (JSON mode) — `call_gemini` now actually reaches Gemini instead of silently falling back to mock every time.
- Added `POST /api/sessions/{id}/evaluate` — the full-transcript evaluator from `CLAUDE.md` (overall score, 4-way breakdown, per-question feedback, top-3 improvements, one model answer), cached on the session, mock-safe.
- `InterviewResults.jsx` renders that evaluation as an "Interviewer's Report" section.
- Resume-aware interviews: parsed resume (skills/projects/experience/education) is now injected into the interview system prompt, with an explicit instruction that at least half the questions must name the candidate's actual projects/skills.
- Conversation memory: each turn now sends the last 20 messages of transcript history to the model, so it stops re-asking settled questions or forgetting corrections (e.g. the candidate's name) mid-interview.
- Per-exam-type personas: SSC/Banking/Campus IT/Campus MBA each now get their own panel names and opening line instead of all falling back to the UPSC "civil services" framing.
- `scripts/tune_prompts.py` — standalone harness to test the resume-parse and evaluation prompts against sample data before touching the UI.
- Model note: this Gemini key's free tier throttles `gemini-2.0-flash`/`gemini-3.5-flash` hard; `GEMINI_MODEL=gemini-flash-lite-latest` in `backend/.env` is what's actually being used.

### 🔜 P1 Backlog

- [ ] Real Razorpay integration (test mode — API ready, UI complete, only payment gateway wiring missing)
- [ ] Hindi TTS voice quality — currently uses the browser's built-in `speechSynthesis` (best available Indian voice), not a dedicated TTS model
- [ ] DAF PDF upload and parsing for fully personalized UPSC Personality Test
- [ ] Emotion Timeline — second-by-second voice confidence graph post-interview
- [ ] Hostile Interviewer Mode — AI that interrupts, challenges, and pressure-tests
- [ ] Daily Samachar auto-refresh — scheduled scraping of The Hindu/PIB every morning

### 🗓 P2 Backlog

- [ ] Salary Negotiation Simulator — AI HR manager, counter-offer scenarios
- [ ] Rejection Decoder — post-rejection analysis from described interview
- [ ] Group Discussion Simulator — 5 AI participants with distinct personalities
- [ ] WhatsApp Bot — ₹99/month voice-note practice via WhatsApp Business API
- [ ] College Enterprise Dashboard — bulk student accounts, placement analytics
- [ ] Verified Interview Certificate — blockchain-anchored, LinkedIn-shareable
- [ ] Offer Probability Engine — data-driven hiring prediction from practice history
- [ ] Body Language Mirror — computer vision eye contact + posture analysis

---

<div align="center">

**Built for every aspirant who deserves a fair shot at their dream**

*— अभ्यासेन सिद्धिः — Excellence through Practice —*

© 2026 Mitharva AI · All Rights Reserved

</div>
