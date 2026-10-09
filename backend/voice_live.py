"""
backend/voice_live.py — real-time voice bridge between the browser and
Gemini Live, powering InterviewRoom's "Live Voice" mode.

WHY A SEPARATE MODULE
    server.py is deliberately a single-file REST backend (see README). This
    bridge is a different shape of thing entirely — a long-lived, per-
    connection async WebSocket handler that owns its own Gemini session — so
    it lives on its own and is mounted onto `app` with one call from
    server.py (see register() at the bottom).

PROTOCOL (browser <-> ws://<host>/api/voice/live)
    First client message (JSON text frame), required:
        {"type": "auth", "token": "<JWT>", "session_id": "<interview session id>"}
    After that:
        client -> server : binary frames = raw 16 kHz, 16-bit PCM mono audio
                            chunks from the mic (~20-100 ms each)
        server -> client : binary frames = 24 kHz, 16-bit PCM mono audio to
                            play back (the interviewer's spoken voice)
                            JSON text frames for everything else:
          {"type": "ready", "voice": "<voice name>"}
          {"type": "state", "state": "listening" | "idle"}
          {"type": "transcript", "role": "user"|"assistant", "text": "...", "speaker": "..."}
          {"type": "evaluation", "evaluation": {...}, "isInterviewComplete": bool}
          {"type": "error", "message": "..."}

VOICE
    Gemini Live fixes ONE voice for the whole session — it cannot swap
    mid-conversation. "Multiple voice options" is delivered as a small named
    set the user (or the session's persona) picks from at session start; see
    VOICE_OPTIONS / _voice_for_session.

This mirrors the exact google-genai Live API calls already proven working in
Mark-LIII's main.py (same SDK family): send_realtime_input(audio=types.Blob),
response.data for audio out, response.server_content.{input,output}_transcription,
response.tool_call.function_calls, session.send_tool_response(...).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

logger = logging.getLogger("mitharva.voice_live")

router = APIRouter()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "models/gemini-3.1-flash-live-preview")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me")
JWT_ALGO = "HS256"

# Every voice offered here is a real Gemini Live prebuilt voice, under a
# short product-facing label. Add/remove freely — nothing else in this file
# needs to change.
VOICE_OPTIONS: dict[str, str] = {
    "formal_male":   "Charon",
    "formal_female": "Kore",
    "warm_male":     "Puck",
    "warm_female":   "Aoede",
    "stern_male":    "Fenrir",
}
DEFAULT_VOICE_KEY = "formal_male"

# session_type -> default voice key, so each interviewer persona has a
# consistent character even when the user hasn't picked one explicitly.
PERSONA_VOICE: dict[str, str] = {
    "upsc":       "formal_male",
    "banking":    "formal_female",
    "campus_it":  "warm_male",
    "ssc":        "formal_female",
    "campus_mba": "warm_female",
}

# Plain OpenAPI-style dict, same shape Mark-LIII's actions/*.py TOOL declarations
# use — this is what the SDK's `tools=[{"function_declarations": [...]}]` expects.
EVAL_TOOL_DECLARATION = {
    "name": "record_evaluation",
    "description": (
        "Call this once, silently, immediately after the candidate finishes "
        "answering — in addition to (not instead of) speaking your next "
        "question out loud afterwards. Never speak the scores or this call "
        "out loud; it is for the dashboard only."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "technicalScore":      {"type": "NUMBER", "description": "0-10"},
            "clarityScore":        {"type": "NUMBER", "description": "0-10"},
            "structureScore":      {"type": "NUMBER", "description": "0-10"},
            "confidenceEstimate":  {"type": "NUMBER", "description": "0-10"},
            "overallScore":        {"type": "NUMBER", "description": "0-10"},
            "keyStrengths":        {"type": "ARRAY", "items": {"type": "STRING"}},
            "improvementAreas":    {"type": "ARRAY", "items": {"type": "STRING"}},
            "liveTip":             {"type": "STRING"},
            "isInterviewComplete": {"type": "BOOLEAN", "description": "true after 10-12 questions"},
        },
        "required": ["overallScore", "isInterviewComplete"],
    },
}


def _voice_for_session(session: dict, user: dict) -> str:
    requested = (user.get("interview_voice") or "").strip()
    if requested in VOICE_OPTIONS:
        return VOICE_OPTIONS[requested]
    key = PERSONA_VOICE.get(session.get("session_type"), DEFAULT_VOICE_KEY)
    return VOICE_OPTIONS[key]


def _live_system_instruction(base_prompt: str) -> str:
    # base_prompt is build_interview_system_prompt()'s output, written for a
    # *text* JSON-only contract. For Live, the model should actually SPEAK the
    # question and use the tool call for scoring instead of JSON text.
    return (
        base_prompt
        + "\n\nYou are now in a LIVE VOICE interview, not a text chat. Speak "
          "naturally and warmly, one question at a time, and wait for the "
          "candidate to finish answering before you respond.\n\n"
          "MANDATORY after every candidate answer, with no exceptions: you "
          "MUST call the record_evaluation function. This is not optional and "
          "not a suggestion — call it immediately once the candidate stops "
          "speaking, before you say anything else. Do this silently; never "
          "speak the scores, the field names, or any JSON out loud. Only "
          "after that function call is made should you speak your next "
          "question aloud."
    )


class LiveBridge:
    """One instance per browser WebSocket connection / interview session."""

    def __init__(self, ws: WebSocket, db, build_system_prompt, get_user_fn, get_session_fn):
        self.ws = ws
        self.db = db
        self.build_system_prompt = build_system_prompt
        self.get_user_fn = get_user_fn
        self.get_session_fn = get_session_fn
        self._closed = False

    async def _send_json(self, payload: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(payload))
        except Exception:
            pass

    async def run(self) -> None:
        # 1. Auth + session handshake — first message only.
        try:
            first = await asyncio.wait_for(self.ws.receive_text(), timeout=10)
            auth = json.loads(first)
        except Exception:
            await self._send_json({"type": "error", "message": "Expected a JSON auth message first."})
            await self.ws.close(code=4001)
            return

        if auth.get("type") != "auth":
            await self._send_json({"type": "error", "message": "First message must be {type: 'auth', ...}."})
            await self.ws.close(code=4001)
            return

        try:
            payload = jwt.decode(auth.get("token", ""), JWT_SECRET, algorithms=[JWT_ALGO])
            user_id = payload.get("sub")
        except Exception:
            await self._send_json({"type": "error", "message": "Invalid or expired token."})
            await self.ws.close(code=4001)
            return

        user = await self.get_user_fn(user_id)
        if not user:
            await self._send_json({"type": "error", "message": "User not found."})
            await self.ws.close(code=4001)
            return

        session = await self.get_session_fn(auth.get("session_id"), user_id)
        if not session:
            await self._send_json({"type": "error", "message": "Interview session not found."})
            await self.ws.close(code=4004)
            return

        if not GEMINI_API_KEY:
            await self._send_json({
                "type": "error",
                "message": "Live voice isn't configured on the server (missing GEMINI_API_KEY). "
                           "Falling back to Whisper mode is recommended.",
            })
            await self.ws.close(code=4000)
            return

        base_prompt = self.build_system_prompt(session, user)
        system_instruction = _live_system_instruction(base_prompt)
        voice_name = _voice_for_session(session, user)

        client = genai.Client(api_key=GEMINI_API_KEY)
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=system_instruction,
            tools=[{"function_declarations": [EVAL_TOOL_DECLARATION]}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        )

        try:
            async with client.aio.live.connect(model=LIVE_MODEL, config=config) as live:
                await self._send_json({"type": "ready", "voice": voice_name})
                await asyncio.gather(
                    self._pump_client_to_gemini(live),
                    self._pump_gemini_to_client(live, session),
                )
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.exception("Live voice session failed: %s", e)
            await self._send_json({"type": "error", "message": str(e)})
        finally:
            self._closed = True

    async def _pump_client_to_gemini(self, live) -> None:
        """Browser mic audio (binary PCM16 @16kHz) -> Gemini Live."""
        try:
            while not self._closed:
                msg = await self.ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data:
                    await live.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm")
                    )
                    continue
                text = msg.get("text")
                if text:
                    try:
                        ctrl = json.loads(text)
                    except Exception:
                        continue
                    if ctrl.get("type") == "end":
                        break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self._closed = True

    async def _pump_gemini_to_client(self, live, session: dict) -> None:
        """Gemini Live audio/transcripts/tool-calls -> browser + DB."""
        try:
            while not self._closed:
                async for response in live.receive():
                    if self._closed:
                        break

                    if response.data:
                        try:
                            await self.ws.send_bytes(response.data)
                        except Exception:
                            self._closed = True
                            break

                    sc = response.server_content
                    if sc:
                        if sc.input_transcription and sc.input_transcription.text:
                            await self._send_json({
                                "type": "transcript", "role": "user",
                                "text": sc.input_transcription.text,
                            })
                        if sc.output_transcription and sc.output_transcription.text:
                            await self._send_json({
                                "type": "transcript", "role": "assistant",
                                "text": sc.output_transcription.text,
                            })
                        if sc.turn_complete:
                            await self._send_json({"type": "state", "state": "idle"})

                    if response.tool_call:
                        await self._handle_tool_call(live, response.tool_call, session)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self._closed = True

    async def _handle_tool_call(self, live, tool_call, session: dict) -> None:
        fn_responses = []
        for fc in tool_call.function_calls:
            if fc.name == "record_evaluation":
                evaluation = dict(fc.args or {})
                is_complete = bool(evaluation.get("isInterviewComplete"))
                try:
                    await self.db.sessions.update_one(
                        {"id": session["id"]},
                        {"$inc": {"questions_count": 1}},
                    )
                except Exception:
                    pass
                await self._send_json({
                    "type": "evaluation",
                    "evaluation": evaluation,
                    "isInterviewComplete": is_complete,
                })
                fn_responses.append(types.FunctionResponse(
                    id=fc.id, name=fc.name, response={"result": "recorded"}
                ))
        if fn_responses:
            await live.send_tool_response(function_responses=fn_responses)


def register(app_router: APIRouter, db, build_system_prompt, get_user_by_id, get_session_by_id) -> None:
    """Call once from server.py to mount the /voice/live WebSocket route.

    get_user_by_id(user_id) -> dict | None
    get_session_by_id(session_id, user_id) -> dict | None
    build_system_prompt(session_dict, user_dict) -> str   (reuse the existing
        build_interview_system_prompt from server.py as-is)
    """

    @app_router.websocket("/voice/live")
    async def voice_live_ws(websocket: WebSocket):
        await websocket.accept()
        bridge = LiveBridge(websocket, db, build_system_prompt, get_user_by_id, get_session_by_id)
        try:
            await bridge.run()
        except WebSocketDisconnect:
            pass
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
