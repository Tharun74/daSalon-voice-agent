import base64
import io
import os
import wave
from typing import Protocol, AsyncIterator
import httpx
from app.voice.stt import BrowserFallback


class TTS(Protocol):
    async def synthesize(self, text: str, language: str, voice: str, pace: float = 1) -> bytes: ...
    def stream(self, texts: AsyncIterator[str], language: str, voice: str, pace: float = 1) -> AsyncIterator[bytes]: ...


class BrowserTTS:
    async def synthesize(self, text, language, voice, pace=1):
        raise BrowserFallback("Use browser speech synthesis.")

    async def stream(self, texts, language, voice, pace=1):
        async for text in texts:
            yield await self.synthesize(text, language, voice, pace)


# ── bulbul:v4-flash — confirmed persona IDs from official Sarvam docs ──────
# Source: https://docs.sarvam.ai/api/api-guides-tutorials/models/bulbul
# Format: <name>_<language>_<style>
V4_PERSONAS = {
    # Female — English customer service (confirmed in official docs)
    "simran":  "simran_en_customer",
    # Female — Hindi devotional (confirmed in official docs)
    "ishita":  "ishita_hi_devotional",
    # Male — English-Hindi ads (confirmed as v4-flash default)
    "shubh":   "shubh_enhi_ads",
}
# Default female persona for the salon receptionist
V4_DEFAULT = "simran_en_customer"

# ── bulbul:v3 — 30+ confirmed named speakers ───────────────────────────────
FEMALE_SPEAKERS_V3 = {
    "ritu", "priya", "neha", "pooja", "simran", "kavya",
    "ishita", "shreya", "roopa", "tanya", "shruti", "suhani",
    "kavitha", "rupali"
}
VALID_SPEAKERS_V3 = FEMALE_SPEAKERS_V3 | {
    "aditya", "ashutosh", "rahul", "rohan", "amit", "dev", "ratan", "varun",
    "manan", "sumit", "kabir", "aayan", "shubh", "advait", "anand",
    "tarun", "sunny", "mani", "gokul", "vijay", "mohit", "rehan", "soham"
}

SUPPORTED_LANGUAGES = {
    "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "mr-IN",
    "bn-IN", "gu-IN", "ml-IN", "pa-IN", "od-IN"
}


class SarvamTTS(BrowserTTS):
    """Sarvam AI TTS.
    - bulbul:v4-flash: 200+ persona voices, pace control only (no pitch/loudness — those are v2 only)
    - bulbul:v3: 30+ named speakers, temperature control for expressiveness
    """

    async def synthesize(self, text, language, voice, pace=1):
        if not text or len(text) > 2500:
            raise BrowserFallback("Speech chunk is empty or too long.")
        lang = language if language in SUPPORTED_LANGUAGES else "en-IN"
        model = os.getenv("TTS_MODEL", "bulbul:v4-flash")

        if model == "bulbul:v4-flash":
            # Use confirmed persona ID; fall back to simran_en_customer (female, English, customer)
            speaker = V4_PERSONAS.get(voice, V4_DEFAULT)
            payload = {
                "text": text,
                "language_code": lang,
                "speaker": speaker,
                "model": "bulbul:v4-flash",
                "pace": max(0.5, min(2.0, pace)),
                "speech_sample_rate": 24000,
                "output_audio_codec": "wav",
            }
        else:
            # v3: temperature controls expressiveness (0.01–1.0); pitch/loudness NOT supported
            speaker = voice if voice in VALID_SPEAKERS_V3 else "ritu"
            payload = {
                "text": text,
                "language_code": lang,
                "speaker": speaker,
                "model": "bulbul:v3",
                "pace": max(0.5, min(2.0, pace)),
                "temperature": float(os.getenv("TTS_TEMPERATURE", "0.6")),
                "speech_sample_rate": 24000,
                "output_audio_codec": "wav",
            }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.sarvam.ai/text-to-speech",
                    headers={"api-subscription-key": os.getenv("SARVAM_API_KEY", "")},
                    json=payload,
                )
                response.raise_for_status()
                return base64.b64decode(response.json()["audios"][0], validate=True)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise BrowserFallback("Speech service unavailable. Using browser voice.") from None


class FakeTTS(BrowserTTS):
    async def synthesize(self, text, language, voice, pace=1):
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(bytes(4800))
        return output.getvalue()


def get_tts(settings=None):
    provider = os.getenv("TTS_PROVIDER", "sarvam").lower()
    if provider == "fake":
        return FakeTTS()
    if provider == "browser" or (settings and settings.provider == "browser"):
        return BrowserTTS()
    if (provider == "sarvam" or not provider) and os.getenv("SARVAM_API_KEY"):
        return SarvamTTS()
    return BrowserTTS()



class FakeTTS(BrowserTTS):
    async def synthesize(self, text, language, voice, pace=1):
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(bytes(4800))
        return output.getvalue()


def get_tts(settings=None):
    provider = os.getenv("TTS_PROVIDER", "sarvam").lower()
    if provider == "fake":
        return FakeTTS()
    if provider == "browser" or (settings and settings.provider == "browser"):
        return BrowserTTS()
    if (provider == "sarvam" or not provider) and os.getenv("SARVAM_API_KEY"):
        return SarvamTTS()
    return BrowserTTS()
