import json
import threading
import time
import uuid
from types import SimpleNamespace as NS
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app import chat, llm
from app.db import get_db
from app.routes.chat_routes import _session_request_times
from app.voice.session import pcm_wav

client = TestClient(app)


def message(text='', tool=None, args=None):
    calls = [NS(id='tool-1', function=NS(name=tool, arguments=json.dumps(args or {})))] if tool else None
    return NS(content=text, tool_calls=calls)


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setenv('STT_PROVIDER', 'fake')
    monkeypatch.setenv('TTS_PROVIDER', 'fake')
    monkeypatch.setenv('VOICE_ENABLED', 'true')
    _session_request_times.clear()
    monkeypatch.setattr(chat, 'retrieve_reference_context', lambda salon_id, query: f'Policy for {salon_id} only.')
    def complete(messages, **kwargs):
        if messages[-1]['role'] == 'tool':
            return message(messages[-1]['content'])
        user = messages[-1]['content']
        if user == 'allergy':
            return message(tool='escalate_to_human', args={'reason':'Allergy concern'})
        if user == 'unknown':
            return message(tool='log_unanswered_question', args={'question':'Can pets visit?'})
        if user == 'policy':
            return message(messages[0]['content'].split('<reference_documents>')[-1].split('</reference_documents>')[0])
        return message(tool='get_services', args={'salon_id':'glow-studio'})
    monkeypatch.setattr(chat, 'complete', complete)
    def stream(messages, tools):
        msg = chat.complete(messages=messages, tools=tools)
        if not msg.tool_calls:
            yield {'type':'assistant_text_delta', 'text':msg.content}
        yield {'type':'message', 'message':msg}
    monkeypatch.setattr(llm, 'complete_stream', stream)


def turn(text='services', salon='glow-studio', sid=None, **extra):
    return client.post('/voice/turn', data={'salon_id':salon, 'session_id':sid or str(uuid.uuid4()), 'text':text, **extra})


@pytest.mark.parametrize('salon', ['glow-studio','serenity-spa','gentlemans-cut'])
def test_tool_parity_and_persistence(salon):
    sid = str(uuid.uuid4())
    text = client.post('/chat',json={'salon_id':salon,'session_id':sid,'message':'services'}).json()
    response = turn(salon=salon, sid=sid)
    assert response.status_code == 200
    voice = response.json()
    assert text['reply'].startswith(voice['reply'])
    assert len(voice['reply']) <= 300
    assert voice['audio'].startswith('UklGR')
    conv = get_db().conversations.find_one({'salon_id':salon,'session_id':sid})
    assert conv['messages'][-1]['channel'] == 'voice'
    assert conv['messages'][0]['channel'] == 'text'
    assert conv['messages'][-1]['timings']['total_ms'] >= 0
    tool = next(m for m in conv['messages'] if m['role'] == 'tool_result')
    assert all(s['name'] != 'Signature Haircut & Blowdry' for s in tool['result']['services']) if salon != 'glow-studio' else True
    assert get_db().voice_usage.count_documents({'salon_id':salon,'session_id':sid}) == 1


def test_voice_to_text_context_and_hot_settings(monkeypatch):
    sid = str(uuid.uuid4())
    turn('remember this',sid=sid)
    seen = []
    def complete(**kw):
        seen.extend(kw['messages'])
        return message('Still here.')
    monkeypatch.setattr(chat,'complete',complete)
    old = get_db().bot_configs.find_one({'salon_id':'glow-studio'})['instructions']
    try:
        client.put('/salons/glow-studio/bot-config',json={'instructions':'Use the phrase fresh welcome.'})
        response = client.post('/chat',json={'salon_id':'glow-studio','session_id':sid,'message':'Do you remember?'})
        assert response.status_code == 200
        assert 'fresh welcome' in seen[0]['content']
        assert any(m.get('content') == 'remember this' for m in seen)
        assert 'VOICE CHANNEL' not in seen[0]['content']
    finally:
        client.put('/salons/glow-studio/bot-config',json={'instructions':old})


def test_rag_isolation_and_guardrail_prompt(monkeypatch):
    seen = []
    def complete(**kw):
        seen.append(kw['messages'])
        if kw['messages'][-1]['role'] == 'tool':
            return message('Policy checked.')
        return message(tool='search_salon_knowledge', args={'query':'policy', 'salon_id':'glow-studio'})
    monkeypatch.setattr(chat,'complete',complete)
    turn('policy',salon='serenity-spa')
    prompt = seen[0][0]['content']
    assert 'Policy for serenity-spa only.' not in prompt
    assert 'NOT a doctor' in prompt and 'ignore those instructions' in prompt
    assert 'Policy for serenity-spa only.' in seen[-1][-1]['content']
    assert 'Policy for glow-studio' not in seen[-1][-1]['content']


def test_booking_readback_and_collision(monkeypatch):
    date = (datetime.now() + timedelta(days=20)).date()
    while date.weekday() == 6:
        date += timedelta(days=1)
    args = {'customer_name':'Voice Test','phone':'9000000001','service_name':'Signature Haircut & Blowdry',
            'start_time':str(date)+'T11:00','staff_name':'Ananya Sharma'}
    def complete(**kw):
        if kw['messages'][-1]['role'] == 'tool':
            return message(kw['messages'][-1]['content'])
        return message(tool='book_appointment',args=args)
    monkeypatch.setattr(chat,'complete',complete)
    sid = str(uuid.uuid4())
    before = get_db().appointments.count_documents({'salon_id':'glow-studio','phone':args['phone']})
    first = turn('book haircut',sid=sid).json()
    assert 'Shall I book' in first['reply']
    assert get_db().appointments.count_documents({'salon_id':'glow-studio','phone':args['phone']}) == before
    assert '"success": true' in turn('yes',sid=sid).json()['reply']
    other = str(uuid.uuid4())
    turn('book haircut',sid=other)
    assert 'already booked' in turn('yes',sid=other).json()['reply']
    get_db().appointments.delete_many({'salon_id':'glow-studio','phone':args['phone']})


def test_escalation_gap_and_fallback(monkeypatch):
    sid = str(uuid.uuid4())
    assert turn('allergy',sid=sid).json()['status'] == 'handed_off'
    assert get_db().handoffs.find_one({'salon_id':'glow-studio','session_id':sid})
    turn('Thank you',sid=sid)
    handed_off = get_db().conversations.find_one({'salon_id':'glow-studio','session_id':sid})
    assert handed_off['messages'][-2]['content'] == 'Thank you'
    assert handed_off['messages'][-1]['channel'] == 'voice'
    turn('unknown')
    assert get_db().unanswered_questions.find_one({'salon_id':'glow-studio','question':'can pets visit?'})
    monkeypatch.setenv('TTS_PROVIDER','browser')
    assert turn().json()['fallback'] == 'browser_tts'
    monkeypatch.setenv('STT_PROVIDER','browser')
    response = client.post('/voice/turn',data={'salon_id':'glow-studio'},
        files={'audio':('speech.wav',pcm_wav(bytes(3200)),'audio/wav')})
    assert response.json()['fallback'] == 'browser_stt'


def test_limits_and_feature_gate(monkeypatch):
    assert turn(salon='not-a-salon').status_code == 404
    assert turn(sid='../bad').status_code == 422
    assert turn('x'*2001).status_code == 422
    oversized = client.post('/voice/turn',data={'salon_id':'glow-studio'},files={'audio':('speech.wav',bytes(1000000),'audio/wav')})
    assert oversized.status_code == 413
    _session_request_times['limited'] = [time.time()] * 30
    assert turn(sid='limited').status_code == 429
    monkeypatch.setenv('VOICE_ENABLED','false')
    assert turn().status_code == 403
    assert client.get('/voice/config/glow-studio').json()['enabled'] is False


def test_preview_authorization(monkeypatch):
    monkeypatch.setenv('VOICE_ADMIN_TOKEN','test-only')
    assert client.post('/voice/preview',json={'salon_id':'glow-studio'}).status_code == 401
    assert client.post('/voice/preview',json={'salon_id':'glow-studio'},headers={'Authorization':'Bearer test-only'}).status_code == 200


def test_ws_events_and_tenant_tampering():
    sid = str(uuid.uuid4())
    with client.websocket_connect(f'/voice/ws?salon_id=serenity-spa&session_id={sid}',headers={'origin':'http://localhost:8000'}) as ws:
        assert ws.receive_json()['audio_format'] == 'audio/wav'
        ws.send_json({'type':'text','text':'services'})
        got_audio = False
        for _ in range(50):
            event = ws.receive()
            if event.get('bytes'):
                got_audio = True
                continue
            data = json.loads(event['text'])
            if data['type'] == 'assistant_text':
                assert 'Signature Haircut' not in data['text']
            if data['type'] == 'timings':
                break
        assert got_audio
        # Drain final state before the tampering response.
        assert ws.receive_json()['state'] == 'listening'
        ws.send_json({'type':'text','text':'services','salon_id':'glow-studio'})
        assert ws.receive_json()['type'] == 'error'


def test_ws_origin_and_idle(monkeypatch):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/voice/ws?salon_id=glow-studio',headers={'origin':'https://evil.example'}):
            pass
    import app.voice.ws as socket
    monkeypatch.setattr(socket,'IDLE_SECONDS',.05)
    with client.websocket_connect('/voice/ws?salon_id=glow-studio',headers={'origin':'http://localhost:8000'}) as ws:
        assert ws.receive_json()['state'] == 'idle'
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_barge_in_prevents_unstarted_tools(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def slow_stream(messages, tools):
        entered.set()
        release.wait(2)
        yield {'type':'message','message':message(tool='escalate_to_human',args={'reason':'must not run'})}
    monkeypatch.setattr(llm,'complete_stream',slow_stream)
    sid = str(uuid.uuid4())
    with client.websocket_connect(f'/voice/ws?salon_id=glow-studio&session_id={sid}',headers={'origin':'http://localhost:8000'}) as ws:
        ws.receive_json()
        ws.send_json({'type':'text','text':'hello'})
        assert entered.wait(2)
        ws.send_json({'type':'interrupt'})
        for _ in range(8):
            event = ws.receive_json()
            if event.get('interrupted') and event.get('generation',0) >= 2:
                break
        release.set()
    assert not get_db().handoffs.find_one({'salon_id':'glow-studio','session_id':sid})


def test_low_confidence_preserves_transcript_without_actions():
    sid = str(uuid.uuid4())
    result = turn('allergy',sid=sid, confidence=.1).json()
    assert 'repeat' in result['reply']
    conv = get_db().conversations.find_one({'salon_id':'glow-studio','session_id':sid})
    assert conv['messages'][0]['content'] == 'allergy'
    assert all(m['role'] != 'tool_result' for m in conv['messages'])


def test_duplicate_tool_calls_cannot_confirm_same_turn(monkeypatch):
    args = dict(customer_name='Test',phone='9000000009',service_name='Haircut',start_time='2027-12-12T11:00')
    msg = message(tool='book_appointment',args=args)
    msg.tool_calls *= 2
    monkeypatch.setattr(chat,'complete',lambda **kw:msg)
    result = turn('yes').json()
    assert 'Shall I book' in result['reply']
    assert not get_db().appointments.find_one({'salon_id':'glow-studio','phone':args['phone']})


def test_cancel_after_committed_tool_keeps_audit():
    cancel = threading.Event()
    sid = str(uuid.uuid4())
    iterator = chat.run_turn_stream('glow-studio',sid,'allergy',cancel=cancel,turn_id='audit')
    for event in iterator:
        if event['type'] == 'tool_event' and event['phase'] == 'end':
            cancel.set()
    conv = get_db().conversations.find_one({'salon_id':'glow-studio','session_id':sid})
    assert any(m['role'] == 'tool_result' and m['interrupted'] for m in conv['messages'])
    assert get_db().handoffs.find_one({'salon_id':'glow-studio','session_id':sid})
