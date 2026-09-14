"""
THROWAWAY A/B test script — Sarvam bulbul:v2 vs bulbul:v3 pronunciation comparison.

Not wired into the app. Does NOT modify server.py or the live /voice/tts flow.
Reuses the exact same request shape as server.py's _sarvam_tts_audio(), reading
the API key from backend/.env only (never hardcoded).

Usage:
    cd backend
    venv\\Scripts\\activate
    python tts_ab_test.py

Output: MP3 files in backend/tts_ab/, one per (model, speaker, language) variant.
"""
import os
import sys
import json
import base64
import asyncio
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
if not SARVAM_API_KEY:
    print("ERROR: SARVAM_API_KEY not found in backend/.env — aborting.")
    sys.exit(1)

OUT_DIR = Path(__file__).parent / "tts_ab"
OUT_DIR.mkdir(exist_ok=True)

EN_TEXT = "Mohammad, tell me about your experience with software development and API integration."
HI_TEXT = "Mohammad, aapka software development ka experience bataiye."

# (label/filename, model, speaker, lang_code, text)
VARIANTS = [
    ("v2_hitesh_en",  "bulbul:v2", "hitesh", "en-IN", EN_TEXT),
    ("v3_hitesh_en",  "bulbul:v3", "hitesh", "en-IN", EN_TEXT),   # v2 speaker name reused on v3 for direct comparison
    ("v3_shubh_en",   "bulbul:v3", "shubh",  "en-IN", EN_TEXT),   # v3 documented default speaker
    ("v3_rahul_en",   "bulbul:v3", "rahul",  "en-IN", EN_TEXT),   # second v3 speaker for comparison
    ("v3_shubh_hi",   "bulbul:v3", "shubh",  "hi-IN", HI_TEXT),   # Hinglish line, v3 default speaker
]


async def call_sarvam_tts(model: str, speaker: str, lang_code: str, text: str) -> bytes:
    """Same request shape as server.py's _sarvam_tts_audio()."""
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {"Content-Type": "application/json; charset=utf-8", "api-subscription-key": SARVAM_API_KEY}
    payload = {
        "inputs": [text[:1500]],
        "target_language_code": lang_code,
        "speaker": speaker,
        "model": model,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with aiohttp.ClientSession() as http:
        async with http.post(url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                err_text = (await resp.text())[:500]
                raise RuntimeError(f"Sarvam TTS HTTP {resp.status}: {err_text}")
            data = await resp.json()
    return base64.b64decode(data["audios"][0])


async def main():
    print(f"Sarvam A/B test — generating {len(VARIANTS)} variant(s) into {OUT_DIR}\n")
    results = []
    for name, model, speaker, lang_code, text in VARIANTS:
        out_path = OUT_DIR / f"{name}.mp3"
        print(f"  {name:20s} model={model:11s} speaker={speaker:8s} lang={lang_code} ... ", end="", flush=True)
        try:
            audio_bytes = await call_sarvam_tts(model, speaker, lang_code, text)
            out_path.write_bytes(audio_bytes)
            print(f"OK ({len(audio_bytes)} bytes)")
            results.append((name, model, speaker, lang_code, str(out_path), "OK"))
        except Exception as e:
            print(f"FAILED: {e}")
            results.append((name, model, speaker, lang_code, None, f"FAILED: {e}"))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for name, model, speaker, lang_code, path, status in results:
        print(f"{name:20s} | model={model:11s} | speaker={speaker:8s} | lang={lang_code} | {status}")
        if path:
            print(f"{'':20s}   -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
