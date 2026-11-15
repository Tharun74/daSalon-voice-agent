"""Bounded voice sessions and transcript-only usage records (single-process demo)."""
import io
import os
import re
import time
import wave
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import HTTPException
from app.db import get_db, persist_mock_data
from app.routes.chat_routes import is_rate_limited
from app.voice.settings import settings_for

MAX_SECONDS = int(os.getenv("VOICE_MAX_UTTERANCE_SECONDS", "30"))
MAX_BYTES = MAX_SECONDS * 32000 + 4096
IDLE_SECONDS = int(os.getenv("VOICE_IDLE_TIMEOUT_SECONDS", "60"))
SESSION_SECONDS = int(os.getenv("VOICE_MAX_SESSION_SECONDS", "900"))
MAX_SESSIONS = int(os.getenv("VOICE_MAX_CONCURRENT_SESSIONS", "10"))
_active = set()
_guard = threading.Lock()


def validate_session(salon_id, session_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", salon_id or ""):
        raise HTTPException(422, "Invalid salon ID")
    if session_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,150}", session_id):
        raise HTTPException(422, "Invalid session ID")
    return settings_for(salon_id)


def limit(salon_id, session_id, ip):
    # Same session budget as /chat, plus a bounded IP budget for voice.
    if is_rate_limited(session_id or f"{salon_id}_anon") or is_rate_limited("voice-ip:" + ip, 60):
        raise HTTPException(429, "Please wait before speaking again.")


@contextmanager
def reserve(salon_id, session_id):
    key = (salon_id, session_id)
    with _guard:
        if key in _active:
            raise HTTPException(409, "This voice session is already active.")
        if len(_active) >= MAX_SESSIONS:
            raise HTTPException(429, "Voice is busy. Please try again shortly.")
        _active.add(key)
    try:
        yield
    finally:
        with _guard:
            _active.discard(key)


def pcm_wav(pcm):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return out.getvalue()


def validate_audio(audio):
    if not audio or len(audio) > MAX_BYTES:
        raise HTTPException(413, "Audio must be at most 30 seconds.")
    try:
        with wave.open(io.BytesIO(audio)) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                raise ValueError()
            seconds = wav.getnframes() / 16000
            if seconds <= 0 or seconds > MAX_SECONDS:
                raise ValueError()
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                raise ValueError()
            return seconds
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(422, "Send mono 16 kHz PCM16 WAV, at most 30 seconds.") from None


def record_usage(salon_id, session_id, seconds, chars, timings=None, turn_id=None):
    db = get_db()
    db.voice_usage.insert_one({"salon_id": salon_id, "session_id": session_id,
        "stt_seconds": seconds, "tts_chars": chars, "created_at": datetime.now(timezone.utc),
        "timings": timings or {}, "turn_id": turn_id})
    if timings:
        # Identify the exact assistant turn rather than racing the newest message.
        query = {"salon_id": salon_id, "session_id": session_id}
        conv = db.conversations.find_one(query)
        if conv:
            for i in range(len(conv.get("messages", [])) - 1, -1, -1):
                msg = conv["messages"][i]
                if msg.get("role") == "assistant" and msg.get("channel") == "voice":
                    if turn_id and msg.get("turn_id") != turn_id:
                        continue
                    db.conversations.update_one(query, {"$set": {f"messages.{i}.timings": timings}})
                    break
    persist_mock_data()


class EndpointDetector:
    """PCM energy endpointing. Tune for the demo room; not a neural VAD."""
    def __init__(self):
        self.buffer = bytearray()
        self.silence_ms = 0
        self.speech_ms = 0
        self.threshold = float(os.getenv("VOICE_VAD_RMS", "0.015"))
        self.endpoint_ms = int(os.getenv("VOICE_ENDPOINT_MS", "700"))

    def feed(self, frame):
        import array
        import math
        if len(frame) % 2 or len(frame) > 32000:
            raise HTTPException(422, "Invalid PCM frame")
        samples = array.array('h', frame)
        if not samples:
            return False, None
        rms = math.sqrt(sum((x / 32768) ** 2 for x in samples) / len(samples))
        speaking = rms >= self.threshold
        duration = len(samples) / 16
        if speaking or self.buffer:
            self.buffer.extend(frame)
            self.speech_ms += duration if speaking else 0
            self.silence_ms = 0 if speaking else self.silence_ms + duration
        if len(self.buffer) > MAX_SECONDS * 32000:
            self.buffer.clear()
            raise HTTPException(413, "Utterance too long; please use shorter sentences.")
        if self.buffer and self.silence_ms >= self.endpoint_ms:
            audio = bytes(self.buffer) if self.speech_ms >= 160 else None
            self.buffer.clear()
            self.silence_ms = self.speech_ms = 0
            return speaking, audio
        return speaking, None
