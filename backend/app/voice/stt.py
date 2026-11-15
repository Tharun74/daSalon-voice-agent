from dataclasses import dataclass
from typing import Protocol, AsyncIterator
import os
import httpx
from app import config


class BrowserFallback(Exception):
    """The client must use browser recognition or offer typing; never fake a transcript."""


@dataclass
class Transcript:
    text: str
    language: str = "en-IN"
    confidence: float | None = None
    seconds: float = 0
    final: bool = True


class STT(Protocol):
    async def transcribe(self, audio_bytes: bytes, mime: str, language_hint: str) -> Transcript: ...
    def stream(self, frames: AsyncIterator[bytes], language_hint: str) -> AsyncIterator[Transcript]: ...


class BrowserSTT:
    async def transcribe(self, audio_bytes, mime, language_hint):
        raise BrowserFallback("Use browser speech recognition or type your message.")

    async def stream(self, frames, language_hint):
        raise BrowserFallback("Provider streaming is unavailable; use browser recognition.")
        yield  # async iterator contract


class SarvamSTT(BrowserSTT):
    """Sarvam AI Speech-to-Text provider using Saaras model."""

    async def transcribe(self, audio_bytes, mime, language_hint):
        key = os.getenv("SARVAM_API_KEY", "")
        if not key:
            raise BrowserFallback("Sarvam API key not configured. Use browser speech recognition or type.")
        extension = {"audio/wav": "wav", "audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg"}.get(
            mime.split(";")[0], "wav"
        )
        data = {"model": os.getenv("SARVAM_STT_MODEL", "saaras:v4")}
        if language_hint:
            data["language_code"] = language_hint
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": key},
                    data=data,
                    files={"file": (f"speech.{extension}", audio_bytes, mime)},
                )
                response.raise_for_status()
                result = response.json()
            text = (result.get("transcript") or "").strip()
            lang = result.get("language_code") or language_hint or "en-IN"
            return Transcript(text, lang, confidence=None)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise BrowserFallback("Speech service unavailable. Please repeat using browser recognition or type.") from None


class FireworksSTT(BrowserSTT):
    """Batch wire contract verified in official fireworks-ai 0.19.20 AudioInference.

    Current docs no longer expose Whisper streaming; do not fabricate its protocol.
    """
    async def transcribe(self, audio_bytes, mime, language_hint):
        base = os.getenv("FIREWORKS_AUDIO_URL", "https://api.fireworks.ai/audio/v3-turbo")
        data = {"model": os.getenv("STT_MODEL", "whisper-v3-turbo"), "response_format": "verbose_json"}
        if language_hint:
            data["language"] = language_hint.split("-")[0]
        extension = {"audio/wav": "wav", "audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg"}.get(mime.split(';')[0], 'wav')
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.post(base.rstrip('/') + "/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {config.FIREWORKS_API_KEY}"},
                    data=data, files={"file": ("speech." + extension, audio_bytes, mime)})
                response.raise_for_status()
                result = response.json()
            segments = result.get("segments") or []
            low = any(s.get("no_speech_prob", 0) > .6 or s.get("avg_logprob", 0) < -1 for s in segments)
            return Transcript(result["text"], language_hint, .2 if low else None, result.get("duration") or 0)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise BrowserFallback("Speech service unavailable. Please repeat using browser recognition or type.") from None


class FakeSTT(BrowserSTT):
    async def transcribe(self, audio_bytes, mime, language_hint):
        return Transcript("What services do you offer?", language_hint, .99, 1)

    async def stream(self, frames, language_hint):
        async for frame in frames:
            if frame:
                yield Transcript("What services", language_hint, .99, final=False)
                break
        yield Transcript("What services do you offer?", language_hint, .99, 1)


def get_stt():
    provider = os.getenv("STT_PROVIDER", "").lower()
    if provider == "fake":
        return FakeSTT()
    if provider == "browser":
        return BrowserSTT()
    if provider == "fireworks" and config.FIREWORKS_API_KEY:
        return FireworksSTT()
    if (provider == "sarvam" or not provider) and os.getenv("SARVAM_API_KEY"):
        return SarvamSTT()
    if provider == "sarvam" and not os.getenv("SARVAM_API_KEY"):
        return BrowserSTT()
    if config.FIREWORKS_API_KEY:
        return FireworksSTT()
    return BrowserSTT()
