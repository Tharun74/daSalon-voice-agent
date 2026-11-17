from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.voice.settings import VoiceSettings
from app.db import get_db, serialize_doc, serialize_list, persist_mock_data

router = APIRouter(prefix="/salons", tags=["salons"])


class BotConfigUpdate(BaseModel):
    voice: Optional[VoiceSettings] = None
    instructions: Optional[str] = None
    tone: Optional[str] = None
    languages: Optional[List[str]] = None
    enabled_tools: Optional[List[str]] = None


@router.get("")
def list_salons():
    """List all salons with brand and profile information."""
    db = get_db()
    salons = list(db.salons.find())
    return serialize_list(salons)


@router.get("/{salon_id}")
def get_salon_details(salon_id: str):
    """Return full detail for a salon (profile, bot config, services, staff, offers)."""
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        raise HTTPException(status_code=404, detail=f"Salon '{salon_id}' not found")

    bot_config = db.bot_configs.find_one({"salon_id": salon_id})
    services = list(db.services.find({"salon_id": salon_id}))
    staff = list(db.staff.find({"salon_id": salon_id}))
    offers = list(db.offers.find({"salon_id": salon_id}))

    return {
        "salon": serialize_doc(salon),
        "services": serialize_list(services),
        "staff": serialize_list(staff),
        "offers": serialize_list(offers),
    }


@router.get('/{salon_id}/bot-config')
def read_bot_config(salon_id: str, request: Request):
    from app.voice.routes import admin_access
    admin_access(request)
    from app.voice.sarvam_config import V4_VOICES
    cfg = serialize_doc(get_db().bot_configs.find_one({'salon_id': salon_id})) or {}
    if cfg:
        cfg['voice'] = VoiceSettings(**(cfg.get('voice') or {})).model_dump()
        cfg['voice_options'] = V4_VOICES
    return cfg

@router.put("/{salon_id}/bot-config")
def update_bot_config(salon_id: str, update: BotConfigUpdate, request: Request):
    """Update salon's bot instructions, tone, or languages."""
    from app.voice.routes import admin_access
    admin_access(request)
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        raise HTTPException(status_code=404, detail=f"Salon '{salon_id}' not found")

    update_fields = {}
    if update.instructions is not None:
        update_fields["instructions"] = update.instructions
    if update.tone is not None:
        update_fields["tone"] = update.tone
    if update.languages is not None:
        update_fields["languages"] = update.languages
    if update.enabled_tools is not None:
        update_fields["enabled_tools"] = update.enabled_tools

    if update.voice is not None:
        from app.voice.routes import admin_access
        admin_access(request)
        update_fields["voice"] = update.voice.model_dump()

    if update_fields:
        db.bot_configs.update_one(
            {"salon_id": salon_id},
            {"$set": update_fields},
            upsert=True,
        )
        persist_mock_data()

    updated = db.bot_configs.find_one({"salon_id": salon_id})
    return serialize_doc(updated)
