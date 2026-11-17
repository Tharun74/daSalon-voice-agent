import os
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from fastapi import HTTPException
from app.db import get_db
from app.voice.sarvam_config import LEGACY_V4_VOICES, V4_VOICES


class VoiceSettings(BaseModel):
    enabled: bool = True
    provider: Literal["sarvam", "browser"] = "sarvam"
    voice_id: Literal["simran", "ritu", "priya", "neha", "kavya", "ishita", "shreya", "rahul", "shubh"] = "simran"
    v4_voice_id: str | None = None
    v4_language_voices: dict[Literal['en-IN', 'hi-IN', 'ta-IN', 'te-IN', 'kn-IN', 'mr-IN', 'bn-IN', 'gu-IN', 'pa-IN'], str] = Field(default_factory=dict)
    language_default: Literal["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "mr-IN", "bn-IN", "gu-IN", "ml-IN", "pa-IN", "od-IN"] = "en-IN"
    pace: float = Field(0.95, ge=0.5, le=2.0)
    greeting: str = Field("Welcome. How can I help you today?", max_length=300)
    filler_enabled: bool = True
    filler_text: str = Field("Sure, one moment.", max_length=120)

    @field_validator('v4_voice_id')
    @classmethod
    def valid_persona(cls, value):
        if value is not None and value not in V4_VOICES:
            raise ValueError('Choose a supported Bulbul v4 persona')
        return value

    @field_validator('v4_language_voices')
    @classmethod
    def valid_overrides(cls, value):
        if any(persona not in V4_VOICES for persona in value.values()):
            raise ValueError('Choose supported Bulbul v4 personas for language overrides')
        return value

    @model_validator(mode='after')
    def migrate_legacy_voice(self):
        if self.v4_voice_id is None:
            self.v4_voice_id = LEGACY_V4_VOICES[self.voice_id]
        return self


def enabled():
    return os.getenv("VOICE_ENABLED", "true").lower() == "true"


def settings_for(salon_id, require_enabled=True):
    if not get_db().salons.find_one({"_id": salon_id}):
        raise HTTPException(404, "Salon not found")
    cfg = get_db().bot_configs.find_one({"salon_id": salon_id}) or {}
    settings = VoiceSettings(**(cfg.get("voice") or {}))
    if require_enabled and (not enabled() or not settings.enabled):
        raise HTTPException(403, "Voice is disabled for this salon")
    return settings


from pathlib import Path

VOICE_ADDENDUM = Path(__file__).with_name('receptionist_prompt.md').read_text(encoding='utf-8')
