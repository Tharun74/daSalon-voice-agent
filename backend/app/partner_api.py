"""Small replaceable mock Partner HTTP API. No connection to real da Salon data."""
import hashlib
import json
import os
import threading
import time
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db import get_db, persist_mock_data
from app.demo_auth import normalize_phone

router = APIRouter(prefix='/mock-partner', tags=['Mock Partner'])
booking_lock = threading.RLock()
READ_TOOLS = {'get_services', 'get_staff', 'get_offers', 'get_hours', 'check_availability'}

def booking_fingerprint(arguments):
    args = {k: str(v).strip() for k, v in arguments.items()
            if k in {'customer_name', 'phone', 'service_name', 'start_time', 'staff_name'} and v is not None}
    if args.get('phone'):
        args['phone'] = normalize_phone(args['phone'])
    return hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()

class ToolRequest(BaseModel):
    arguments: dict = Field(default_factory=dict)
    session_id: str = Field(default='', max_length=100)

@router.post('/{salon_id}/{operation}')
def partner_operation(salon_id: str, operation: str, payload: ToolRequest):
    from app.tools import TOOL_DISPATCH
    db = get_db()
    if not db.salons.find_one({'_id': salon_id}):
        raise HTTPException(404, 'Salon not found')
    args = {k: v for k, v in payload.arguments.items() if k != 'salon_id'}
    if operation in READ_TOOLS:
        try:
            return TOOL_DISPATCH[operation](salon_id=salon_id, **args)
        except (TypeError, ValueError):
            raise HTTPException(422, 'Invalid request parameters')
    if operation not in {'book_appointment', 'get_booking_status'}:
        raise HTTPException(404, 'Unsupported operation')
    with booking_lock:
        conv_key = {'salon_id': salon_id, 'session_id': payload.session_id}
        conv = db.conversations.find_one(conv_key) or {}
        try:
            fingerprint = booking_fingerprint(args)
        except ValueError:
            raise HTTPException(422, 'Invalid phone number')
        previous = db.booking_requests.find_one({**conv_key, 'fingerprint': fingerprint})
        if operation == 'get_booking_status':
            return previous['result'] if previous else {'success': False, 'status': 'unknown', 'message': 'No confirmed result is available yet.'}
        if previous:
            return previous['result']
        try:
            phone = normalize_phone(args.get('phone', ''))
        except ValueError:
            phone = ''
        if not payload.session_id or not phone or conv.get('demo_phone') != phone:
            db.conversations.update_one(conv_key, {'$set': {'phone_required': True}}, upsert=True)
            persist_mock_data()
            return {'success': False, 'phone_required': True,
                    'message': 'Complete the demo phone step in the panel. Any six-digit code is accepted; no SMS is sent.'}
        args['phone'] = phone
        consent = conv.get('booking_consent') or {}
        if consent.get('fingerprint') != fingerprint or consent.get('expires', 0) <= time.time():
            return {'success': False, 'confirmation_required': True,
                    'message': 'Read back the exact appointment and obtain explicit confirmation before booking.'}
        from app.tools import _find_service
        service = _find_service(salon_id, str(args.get('service_name', '')))
        quote = {'price': service.get('price'), 'duration_min': service.get('duration_min')} if service else None
        if consent.get('quote') != quote:
            return {'success': False, 'confirmation_required': True, 'price_changed': True,
                    'message': 'Service price or duration changed. Read back the updated details and ask again.'}
        try:
            result = TOOL_DISPATCH[operation](salon_id=salon_id, **args)
        except (TypeError, ValueError):
            raise HTTPException(422, 'Invalid booking details')
        if result.get('success'):
            result['demo_only'] = True
            db.booking_requests.insert_one({**conv_key, 'fingerprint': fingerprint, 'result': result})
            db.conversations.update_one(conv_key, {'$set': {'last_booking': result, 'phone_required': False}, '$unset': {'booking_consent': '', 'unresolved_booking': ''}})
            persist_mock_data()
        return result

def call_partner(operation, arguments, salon_id, session_id=None):
    """Only this adapter changes when an authorized Partner API is provided."""
    base = os.getenv('PARTNER_API_BASE_URL', f"http://127.0.0.1:{os.getenv('PORT', '8001')}/mock-partner").rstrip('/')
    try:
        response = httpx.post(f'{base}/{salon_id}/{operation}',
            json={'arguments': arguments, 'session_id': session_id or ''}, timeout=12)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        if operation == 'book_appointment':
            # A lost response can follow a successful write. Read the original
            # request's result; never issue a second write to guess its outcome.
            try:
                status = httpx.post(f'{base}/{salon_id}/get_booking_status',
                    json={'arguments': arguments, 'session_id': session_id or ''}, timeout=12)
                status.raise_for_status()
                result = status.json()
                if result.get('success'):
                    return result
            except (httpx.HTTPError, ValueError):
                pass
            return {'success': False, 'status': 'unknown',
                    'message': 'The booking result is unknown. Check the original request before attempting another appointment.'}
        return {'success': False, 'error': 'Salon data is temporarily unavailable. Please try again; do not confirm a booking.'}
