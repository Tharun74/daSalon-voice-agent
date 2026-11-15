from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app import chat


def test_chat_contract_and_history(monkeypatch):
    seen = []
    def complete(**kwargs):
        seen.append(kwargs['messages'])
        return SimpleNamespace(content='Hello from the same brain.', tool_calls=None)
    monkeypatch.setattr(chat, 'complete', complete)
    monkeypatch.setattr(chat, 'retrieve_reference_context', lambda **kw: None)
    client = TestClient(app)
    payload = dict(salon_id='glow-studio', session_id='contract-test', message='Hello')
    response = client.post('/chat', json=payload)
    assert response.json() == dict(reply='Hello from the same brain.',
                                   session_id='contract-test', status='active')
    client.post('/chat', json={**payload, 'message': 'Remember me?'})
    assert seen[-1][-3]['content'] == 'Hello'
    conv = get_db().conversations.find_one({'salon_id':'glow-studio','session_id':'contract-test'})
    assert [m['role'] for m in conv['messages']] == ['user','assistant','user','assistant']
    assert all(m['channel'] == 'text' for m in conv['messages'])
    assert client.post('/chat', json={**payload, 'salon_id':'missing'}).status_code == 404
    assert client.post('/chat', json={**payload, 'message':''}).status_code == 422
