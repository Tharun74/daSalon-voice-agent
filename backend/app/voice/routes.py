import asyncio
import base64
import os
import secrets
import time
import uuid
from fastapi import APIRouter, File, Form, UploadFile, Request, HTTPException
from pydantic import BaseModel, Field
from app.chat import run_turn
from app.db import get_db
from app.voice import stt, tts
from app.voice.formatter import speakable, language_for, SentenceChunker
from app.voice.settings import settings_for, enabled
from app.voice.sarvam_config import speech_profile
from app.voice.session import validate_session, validate_audio, limit, reserve, record_usage, MAX_BYTES

router = APIRouter(prefix="/voice", tags=["voice"])

# ---------------------------------------------------------------------------
# Voice warm-up caches (populated at startup via warmup_voice_cache())
# ---------------------------------------------------------------------------
_greeting_cache: dict[str, bytes] = {}
_filler_cache: dict[str, bytes] = {}

FILLER_TEXTS = [
    "One moment, let me check that for you.",
    "Sure, one second.",
    "Ek second, main check karta hun.",
]


async def warmup_voice_cache():
    """Load MCP-generated fixed phrases; never block app startup on synthesis."""
    from app.voice.cache import cache_path
    for salon_id in ["glow-studio", "serenity-spa", "gentlemans-cut"]:
        cfg = settings_for(salon_id, require_enabled=False)
        path = cache_path(cfg, cfg.greeting, cfg.language_default)
        if path.exists():
            _greeting_cache[salon_id] = path.read_bytes()


def admin_access(request: Request):
    token = os.getenv("VOICE_ADMIN_TOKEN", "")
    if token:
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            raise HTTPException(401, "Owner authorization required")
    elif os.getenv('RAILWAY_ENVIRONMENT_ID') or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Configure owner authorization for remote dashboard access")


@router.get("/config/{salon_id}")
def public_config(salon_id: str):
    cfg = settings_for(salon_id, require_enabled=False)
    model, voice = speech_profile(cfg.voice_id, cfg.language_default)
    return {**cfg.model_dump(), "enabled": enabled() and cfg.enabled,
            "tts_model": model, "tts_voice_id": voice,
            "stt": "browser" if cfg.provider == 'browser' or type(stt.get_stt()) is stt.BrowserSTT else "server",
            "tts": "browser" if type(tts.get_tts(cfg)) is tts.BrowserTTS else "server",
            "streaming_stt": bool(os.getenv("SARVAM_API_KEY")) and cfg.provider != 'browser', "input_format": "pcm_s16le", "sample_rate": 16000,
            "notice": "You are speaking with an AI assistant. Your conversation is transcribed."}


async def speech_output(reply, cfg):
    language = language_for(reply, cfg.language_default)
    text = speakable(reply, normalize_numbers=speech_profile(cfg.voice_id, language)[0] != "bulbul:v4-flash")
    audios = []
    started = time.perf_counter()
    first_byte = None
    try:
        chunks = SentenceChunker(limit=500).feed(text, final=True)
        if not chunks and text.strip():
            chunks = [text.strip()]
        tts_engine = tts.get_tts(cfg)
        # Synthesize first sentence immediately, then rest concurrently — reduces latency.
        if chunks:
            first_audio = await tts_engine.synthesize(chunks[0], language, cfg.voice_id, cfg.pace)
            first_byte = round((time.perf_counter() - started) * 1000)
            audios.append(base64.b64encode(first_audio).decode())
            if len(chunks) > 1:
                rest = await asyncio.gather(*[
                    tts_engine.synthesize(c, language, cfg.voice_id, cfg.pace) for c in chunks[1:]
                ])
                for chunk_audio in rest:
                    audios.append(base64.b64encode(chunk_audio).decode())
    except stt.BrowserFallback:
        return {"audio": None, "audio_chunks": [], "fallback": "browser_tts",
                "speech_text": text, "language": language, "tts_first_byte_ms": first_byte}
    return {"audio": audios[0] if audios else None, "audio_chunks": audios,
            "audio_mime": "audio/wav", "speech_text": text, "language": language,
            "tts_first_byte_ms": first_byte}


@router.post("/turn")
async def voice_turn(request: Request, salon_id: str = Form(...), session_id: str = Form(""),
                     audio: UploadFile | None = File(None), text: str = Form(""),
                     confidence: float | None = Form(None)):
    started = time.perf_counter()
    cfg = validate_session(salon_id, session_id)
    session_id = session_id or str(uuid.uuid4())
    limit(salon_id, session_id, request.client.host)
    if confidence is not None and not 0 <= confidence <= 1:
        raise HTTPException(422, "Invalid recognition confidence")
    with reserve(salon_id, session_id):
        seconds = 0
        if audio:
            data = await audio.read(MAX_BYTES + 1)
            seconds = validate_audio(data)
            try:
                transcript = await stt.get_stt().transcribe(data, "audio/wav", cfg.language_default)
                text, confidence = transcript.text, transcript.confidence
            except stt.BrowserFallback as exc:
                return {"fallback": "browser_stt", "detail": str(exc), "session_id": session_id}
        stt_ms = (time.perf_counter() - started) * 1000
        if not text.strip() or len(text) > 2000:
            raise HTTPException(422, "Please speak a message of at most 2000 characters.")
        turn_id = str(uuid.uuid4())
        # Low confidence goes through the shared prompt/history but cannot execute tools.
        uncertain = confidence is not None and confidence < .5
        llm_start = time.perf_counter()
        result = await asyncio.to_thread(run_turn, salon_id, session_id, text, "voice",
            execute_tools=not uncertain, turn_id=turn_id, uncertain=uncertain)
        llm_ms = (time.perf_counter() - llm_start) * 1000
        tts_start = time.perf_counter()
        speech = await speech_output(result["reply"], cfg)
        timings = {"stt_ms": round(stt_ms), "llm_first_token_ms": None,
                   "llm_ms": round(llm_ms), "tts_first_byte_ms": speech["tts_first_byte_ms"],
                   "tts_ms": round((time.perf_counter() - tts_start)*1000),
                   "total_ms": round((time.perf_counter() - started)*1000)}
        record_usage(salon_id, session_id, seconds, len(speech["speech_text"]) if speech["audio"] else 0, timings, turn_id)
        return {**result, "transcript": text, **speech, "timings": timings}


class Preview(BaseModel):
    salon_id: str
    text: str = Field("Welcome. How can I help you today?", min_length=1, max_length=300)


@router.post("/preview")
async def preview(payload: Preview, request: Request):
    admin_access(request)
    cfg = settings_for(payload.salon_id)
    limit(payload.salon_id, "preview:" + payload.salon_id, request.client.host)
    result = await speech_output(payload.text, cfg)
    record_usage(payload.salon_id, "preview", 0, len(result["speech_text"]) if result["audio"] else 0)
    return result


@router.get("/usage/{salon_id}")
def usage(salon_id: str, request: Request):
    admin_access(request)
    settings_for(salon_id, require_enabled=False)
    records = list(get_db().voice_usage.find({"salon_id": salon_id}))
    return {"stt_seconds": round(sum(r.get("stt_seconds", 0) for r in records), 2),
            "tts_chars": sum(r.get("tts_chars", 0) for r in records)}
