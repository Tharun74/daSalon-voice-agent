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
        # Sentence-level synthesis: bounded chunks can be cancelled between requests.
        async for text in texts:
            yield await self.synthesize(text, language, voice, pace)


VALID_SPEAKERS = {
    "aditya", "ritu", "ashutosh", "priya", "neha", "rahul", "pooja", "rohan",
    "simran", "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun",
    "manan", "sumit", "roopa", "kabir", "aayan", "shubh", "advait", "anand",
    "tanya", "tarun", "sunny", "mani", "gokul", "vijay", "shruti", "suhani",
    "mohit", "kavitha", "rehan", "soham", "rupali"
}

SUPPORTED_LANGUAGES = {
    "en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "mr-IN",
    "bn-IN", "gu-IN", "ml-IN", "pa-IN", "od-IN"
}


class SarvamTTS(BrowserTTS):
    async def synthesize(self, text, language, voice, pace=1):
        if not text or len(text) > 2500:
            raise BrowserFallback("Speech chunk is empty or too long.")
        speaker = voice if voice in VALID_SPEAKERS else "priya"
        lang = language if language in SUPPORTED_LANGUAGES else "en-IN"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post("https://api.sarvam.ai/text-to-speech",
                    headers={"api-subscription-key": os.getenv("SARVAM_API_KEY", "")},
                    json={"text": text, "language_code": lang, "speaker": speaker,
                          "model": "bulbul:v3", "pace": pace,
                          "speech_sample_rate": 24000, "output_audio_codec": "wav"})
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
