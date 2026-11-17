import os
from typing import Literal
from pydantic import BaseModel, Field
from fastapi import HTTPException
from app.db import get_db


class VoiceSettings(BaseModel):
    enabled: bool = True
    provider: Literal["sarvam", "browser"] = "sarvam"
    voice_id: Literal["simran", "ritu", "priya", "neha", "kavya", "ishita", "shreya", "rahul", "shubh"] = "simran"
    language_default: Literal["en-IN", "hi-IN", "ta-IN", "te-IN", "kn-IN", "mr-IN", "bn-IN", "gu-IN", "ml-IN", "pa-IN", "od-IN"] = "en-IN"
    pace: float = Field(0.95, ge=0.5, le=2.0)
    greeting: str = Field("Welcome. How can I help you today?", max_length=300)
    filler_enabled: bool = True
    filler_text: str = Field("Sure, one moment.", max_length=120)


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
