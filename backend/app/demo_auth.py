"""Demo phone acknowledgement. This intentionally does NOT verify phone ownership."""
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db import get_db, persist_mock_data

router = APIRouter(prefix='/demo', tags=['Demo phone step'])

def normalize_phone(phone):
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        digits = '91' + digits
    if not 10 <= len(digits) <= 15:
        raise ValueError('Enter a valid phone number with country code.')
    return '+' + digits

class DemoPhone(BaseModel):
    salon_id: str
    session_id: str = Field(min_length=8, max_length=100)
    phone: str
    code: str = Field(pattern=r'^[0-9]{6}$')

@router.post('/phone')
def accept_demo_code(payload: DemoPhone):
    db = get_db()
    if not db.salons.find_one({'_id': payload.salon_id}):
        raise HTTPException(404, 'Salon not found')
    try:
        phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.conversations.update_one({'salon_id': payload.salon_id, 'session_id': payload.session_id},
        {'$set': {'demo_phone': phone, 'phone_required': False},
         '$unset': {'booking_consent': ''},
         '$setOnInsert': {'messages': [], 'status': 'active'}}, upsert=True)
    persist_mock_data()
    return {'accepted': True, 'demo_only': True, 'phone': phone}

@router.get('/session/{salon_id}/{session_id}')
def session_state(salon_id: str, session_id: str, include_history: bool = False):
    conv = get_db().conversations.find_one({'salon_id': salon_id, 'session_id': session_id}) or {}
    import time
    pending = conv.get('voice_pending_booking') or {}
    review = None
    if pending.get('armed') and pending.get('expires', 0) > time.time() and not conv.get('unresolved_booking'):
        args = pending.get('args', {})
        review = {key: args.get(key) for key in ('service_name', 'staff_name', 'start_time', 'customer_name')}
        review.update(pending.get('quote') or {})
    result = {'phone_required': bool(conv.get('phone_required')), 'phone': conv.get('demo_phone'),
            'booking': conv.get('last_booking'), 'review': review,
            'booking_status': 'unknown' if conv.get('unresolved_booking') else ('review' if review else 'idle'), 'demo_only': True}
    if include_history:
        result['messages'] = [{'role': message['role'], 'content': message.get('content', '')}
                              for message in conv.get('messages', [])
                              if message.get('role') in {'user', 'assistant'} and message.get('content')]
    return result
