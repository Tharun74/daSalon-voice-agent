from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.tools import tool_check_availability, _get_tz
from app.llm import clean_content
from app.partner_api import booking_fingerprint
from app.tools import _find_service
import time

client = TestClient(app)
SALON = 'glow-studio'

def slot():
    day = datetime.now(_get_tz()).date() + timedelta(days=14)
    while day.weekday() == 6:
        day += timedelta(days=1)
    data = tool_check_availability(SALON, 'Signature Haircut & Blowdry', str(day), 'Ananya Sharma')
    return data['slot_details'][0]['start_time_iso']

def accept(session, code='123456', phone='9876543210'):
    return client.post('/demo/phone', json={'salon_id':SALON,'session_id':session,'phone':phone,'code':code})

def book(session, start, **extra):
    args = {'customer_name':'Demo Guest','phone':'9876543210','service_name':'Signature Haircut & Blowdry',
            'start_time':start,'staff_name':'Ananya Sharma',**extra}
    service = _find_service(SALON, args['service_name'])
    get_db().conversations.update_one({'salon_id': SALON, 'session_id': session}, {'$set': {
        'booking_consent': {'fingerprint': booking_fingerprint(args), 'expires': time.time()+300,
                            'quote': {key: service.get(key) for key in ('price', 'duration_min')}}}}, upsert=True)
    return client.post(f'/mock-partner/{SALON}/book_appointment',json={'session_id':session,'arguments':args}).json()

def test_demo_accepts_any_six_digits_not_other_formats():
    session = str(uuid4())
    for code in ['000000','999999','548213']:
        result = accept(session, code)
        assert result.status_code == 200
        assert result.json()['demo_only'] is True
    for code in ['12345','1234567','abcdef','１２３４５６']:
        assert accept(session,code).status_code == 422

def test_booking_requires_phone_step_and_matching_phone():
    session = str(uuid4())
    start = slot()
    assert book(session,start)['phone_required']
    accept(session)
    assert book(session,start,phone='9876543211')['phone_required']

def test_booking_retries_are_idempotent_and_slot_is_occupied():
    session = str(uuid4())
    start = slot()
    accept(session)
    first, second = book(session,start), book(session,start)
    assert first['success']
    assert second['booking_id'] == first['booking_id']
    other = str(uuid4()); accept(other)
    assert book(other,start)['success'] is False
    state = client.get(f'/demo/session/{SALON}/{session}').json()
    assert state['booking']['booking_id'] == first['booking_id']

def test_concurrent_booking_only_one_wins():
    sessions = [str(uuid4()),str(uuid4())]
    for session in sessions: accept(session)
    start = slot()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda s: book(s,start),sessions))
    assert sum(r.get('success',False) for r in results) == 1

def test_stylist_must_be_qualified():
    day = (datetime.now(_get_tz()).date()+timedelta(days=15)).isoformat()
    result = tool_check_availability(SALON, 'Gel Manicure & Nail Art',day,'Ananya Sharma')
    assert not result['available']

def test_public_profile_does_not_include_owner_instructions():
    assert 'bot_config' not in client.get(f'/salons/{SALON}').json()

def test_owner_token_applies_to_all_settings_and_documents(monkeypatch):
    monkeypatch.setenv('VOICE_ADMIN_TOKEN','local-test-only')
    assert client.get(f'/salons/{SALON}/bot-config').status_code == 401
    assert client.put(f'/salons/{SALON}/bot-config',json={'tone':'Changed'}).status_code == 401
    assert client.get(f'/salons/{SALON}/documents').status_code == 401
    assert client.get(f'/salons/{SALON}/bot-config',headers={'Authorization':'Bearer local-test-only'}).status_code == 200

def test_reasoning_is_never_customer_text():
    assert clean_content('<|channel|>analysis<|message|>internal draft') == ''
    assert clean_content('<|channel|>analysis<|message|>draft<|channel|>final<|message|>Hello<|return|>') == 'Hello'
