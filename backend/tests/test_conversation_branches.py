"""Behavioral regressions use a scripted model and the real mock Partner boundary."""
import json
import time
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app import chat
from app.main import app
from app.db import get_db
from app.partner_api import partner_operation, ToolRequest, call_partner, booking_fingerprint
from app.tools import _find_service, tool_check_availability, _get_tz, execute_tool_call
from datetime import datetime, timedelta

SALON = 'glow-studio'
client = TestClient(app)

def args():
    day = datetime.now(_get_tz()).date() + timedelta(days=40)
    while day.weekday() == 6:
        day += timedelta(days=1)
    data = tool_check_availability(SALON, 'Signature Haircut & Blowdry', str(day), 'Ananya Sharma')
    return dict(service_name='Signature Haircut & Blowdry', staff_name='Ananya Sharma',
                start_time=data['slot_details'][0]['start_time_iso'], customer_name='Test Guest', phone='9876543210')

def tool_message(arguments):
    return SimpleNamespace(content='', tool_calls=[SimpleNamespace(id=str(uuid4()),
        function=SimpleNamespace(name='book_appointment', arguments=json.dumps(arguments)))])

@pytest.fixture
def brain(monkeypatch):
    session = str(uuid4())
    booking = args()
    monkeypatch.setattr(chat, 'retrieve_reference_context', lambda **kw: None)
    monkeypatch.setattr(chat, 'complete', lambda **kw: tool_message(booking))
    monkeypatch.setattr(chat, 'execute_tool_call', lambda tool_name, arguments, salon_id, session_id:
        partner_operation(salon_id, tool_name, ToolRequest(arguments=arguments, session_id=session_id)))
    return session, booking

def turn(session, text):
    return chat.run_turn(SALON, session, text, reference_docs='')

def phone(session):
    assert client.post('/demo/phone', json=dict(salon_id=SALON, session_id=session, phone='9876543210', code='000000')).status_code == 200

def test_complete_flow_preserves_draft_through_phone_step(brain):
    session, booking = brain
    assert 'Please confirm' in turn(session, 'Book my haircut')['reply']
    assert 'phone form' in turn(session, 'Yes, book it.')['reply']
    assert get_db().conversations.find_one({'session_id':session})['voice_pending_booking']['args'] == booking
    phone(session)
    assert 'Please confirm' in turn(session, 'My demo phone step is complete. Please continue.')['reply']
    assert 'demo appointment is booked' in turn(session, 'Yes, book it.')['reply']
    assert get_db().booking_requests.count_documents({'session_id':session}) == 1

def test_detour_yes_cannot_approve_old_readback(brain, monkeypatch):
    session, booking = brain
    phone(session)
    turn(session, 'Book my haircut')
    monkeypatch.setattr(chat, 'complete', lambda **kw: SimpleNamespace(content='I am the salon AI. Is that clear?', tool_calls=None))
    turn(session, 'Are you a robot?')
    monkeypatch.setattr(chat, 'complete', lambda **kw: tool_message(booking))
    assert 'Please confirm' in turn(session, 'yes')['reply']
    assert get_db().booking_requests.count_documents({'session_id':session}) == 0

def test_stop_clears_draft_without_canceling_existing(brain):
    session, _ = brain
    turn(session, 'Book my haircut')
    result = turn(session, 'stop')
    assert 'unchanged' in result['reply']
    assert get_db().conversations.find_one({'session_id':session})['voice_pending_booking'] is None

def test_changed_details_require_readback(brain):
    session, booking = brain
    phone(session)
    turn(session, 'Book my haircut')
    booking['customer_name'] = 'Changed Guest'
    assert 'Please confirm' in turn(session, 'yes')['reply']
    assert get_db().booking_requests.count_documents({'session_id':session}) == 0

def test_api_rejects_booking_without_server_consent():
    session = str(uuid4()); phone(session)
    result = partner_operation(SALON, 'book_appointment', ToolRequest(arguments=args(), session_id=session))
    assert result['confirmation_required']

def test_price_change_requires_new_confirmation(brain):
    session, booking = brain
    phone(session); turn(session, 'Book my haircut')
    service = _find_service(SALON, booking['service_name'])
    try:
        get_db().services.update_one({'_id':service['_id']}, {'$inc':{'price':100}})
        assert 'Please confirm' in turn(session, 'yes')['reply']
        assert get_db().booking_requests.count_documents({'session_id':session}) == 0
    finally:
        get_db().services.update_one({'_id':service['_id']}, {'$set':{'price':service['price']}})

def test_write_timeout_recovers_original_result(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        if url.endswith('/book_appointment'):
            raise httpx.ReadTimeout('response lost')
        return httpx.Response(200, json={'success':True, 'booking_id':'original'}, request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx, 'post', post)
    assert call_partner('book_appointment', args(), SALON, 'session')['booking_id'] == 'original'
    assert len(calls) == 2 and calls[1].endswith('/get_booking_status')

def test_unknown_write_does_not_claim_failure(monkeypatch):
    def post(*a, **kw): raise httpx.ReadTimeout('offline')
    monkeypatch.setattr(httpx, 'post', post)
    assert call_partner('book_appointment', args(), SALON, 'session')['status'] == 'unknown'

def test_unsupported_actions_cannot_be_enabled_by_owner():
    for operation in ('cancel_appointment','escalate_to_human'):
        assert execute_tool_call(operation, {}, SALON)['unsupported']

def test_human_contact_does_not_promise_transfer(brain):
    session, _ = brain
    assert "can't transfer" in turn(session, 'talk to a human')['reply']
    assert get_db().handoffs.count_documents({'session_id':session}) == 0

def test_unresolved_write_blocks_new_booking(brain, monkeypatch):
    from app import partner_api
    session, booking = brain
    get_db().conversations.update_one({'salon_id':SALON, 'session_id':session},
        {'$set':{'unresolved_booking':booking, 'messages':[]}}, upsert=True)
    monkeypatch.setattr(partner_api, 'call_partner', lambda *a, **kw: {'status':'unknown', 'success':False})
    monkeypatch.setattr(chat, 'complete', lambda **kw: pytest.fail('Must reconcile before calling model'))
    assert 'still unknown' in turn(session, 'Book a different appointment')['reply']
    assert get_db().booking_requests.count_documents({'session_id':session}) == 0

def test_expired_server_consent_cannot_write():
    session = str(uuid4()); phone(session)
    booking = args(); service = _find_service(SALON, booking['service_name'])
    get_db().conversations.update_one({'session_id':session}, {'$set':{'booking_consent':{
        'fingerprint':booking_fingerprint(booking), 'expires':time.time()-1,
        'quote':{k:service.get(k) for k in ('price','duration_min')}}}})
    result = partner_operation(SALON, 'book_appointment', ToolRequest(arguments=booking, session_id=session))
    assert result['confirmation_required']
