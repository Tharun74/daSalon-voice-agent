import asyncio
import base64
import json
from types import SimpleNamespace
import pytest
from app.llm import SpeechBudget
from app.voice.live import is_backchannel
from app.voice.settings import VoiceSettings
from app.voice.streaming import LiveSTT, LiveTTS
from app.voice import streaming
from app.voice.confirmation import is_yes


def test_stream_budget_across_token_boundaries():
    cap=SpeechBudget()
    pieces=[cap.feed(x) for x in ['Hello. ', 'Which day', '? ', 'Here are all our prices.']]
    assert ''.join(pieces).strip() == 'Hello. Which day?'
    assert cap.feed('more') == ''
    cap=SpeechBudget()
    assert len(cap.feed('word '*100).split()) == 45


def test_confirmation_is_not_globally_suppressed():
    assert is_backchannel('Hmm...')
    assert not is_backchannel('okay, tomorrow instead')
    assert is_yes('okay')
    assert is_yes('ஆம்')


def test_stream_protocol_and_cancel_cleanup(monkeypatch):
    class Socket:
        def __init__(self):
            self.sent=[];self.closed=False
        async def send(self,text):self.sent.append(json.loads(text))
        async def recv(self):return json.dumps({'type':'audio','data':{'content_type':'audio/pcm','audio':base64.b64encode(bytes(640)).decode()}})
        async def close(self):self.closed=True
    sockets=[];queries=[]
    async def connect(path, query):
        queries.append(query);s=Socket();sockets.append(s);return s
    monkeypatch.setattr(streaming,'socket',connect)
    async def check():
        stt=await LiveSTT().open()
        await stt.audio(bytes(640))
        assert queries[0]['language_code']=='auto' and queries[0]['mode']=='codemix'
        assert sockets[0].sent[0]['event']=='audio_input'
        cfg=VoiceSettings(voice_id='priya');tts=await LiveTTS(cfg).open();cfg.voice_id='rahul'
        stream=tts.stream('Hello','ta-IN')
        assert len(await anext(stream))==640
        assert sockets[1].sent[0]['data']['speaker']=='priya'
        assert sockets[1].sent[0]['data']['language_code']=='ta-IN'
        await stream.aclose()
        assert sockets[1].closed
        await stt.close()
    asyncio.run(check())


def test_live_socket_multiple_turns_and_backchannel(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice import live
    events=asyncio.Queue  # Created inside the serving loop.
    class STT:
        async def open(self):self.q=events();return self
        async def audio(self, pcm):
            text={b'\x01\x00':'haircut',b'\x02\x00':'hmm',b'\x03\x00':'tomorrow'}[pcm]
            await self.q.put({'event':'vad.speech_start'})
            await self.q.put({'event':'transcript.final','text':text,'language':'en-IN'})
        async def events(self):
            while True:yield await self.q.get()
        async def close(self):pass
    class TTS:
        def __init__(self,cfg):pass
        async def open(self):return self
        async def stream(self,text,language):yield bytes(480)
        async def close(self):pass
    calls=[]
    def turns(salon,session,text,**kw):
        calls.append(text)
        yield {'type':'assistant_text_delta','text':'Which day?'}
        yield {'type':'result','result':{'reply':'Which day?','status':'active'}}
    monkeypatch.setenv('SARVAM_API_KEY','fake-test-key')
    monkeypatch.setenv('STT_PROVIDER','sarvam')
    monkeypatch.setenv('VOICE_ALLOWED_ORIGINS','http://localhost:3000')
    monkeypatch.setattr(live,'LiveSTT',STT);monkeypatch.setattr(live,'LiveTTS',TTS)
    monkeypatch.setattr(live,'run_turn_stream',turns)
    with TestClient(app).websocket_connect('/voice/ws?salon_id=glow-studio&session_id=live-stream-test',headers={'origin':'http://localhost:3000'}) as ws:
        def until(kind):
            for _ in range(50):
                e=ws.receive_json()
                if e['type']==kind:return e
            raise AssertionError(kind)
        until('audio_end')
        ws.send_json({'type':'playback_done'})
        ws.send_bytes(b'\x01\x00');until('audio_end')
        ws.send_bytes(b'\x02\x00');until('playback_resume')
        assert calls==['haircut']
        ws.send_bytes(b'\x03\x00');until('audio_end')
        assert calls==['haircut','tomorrow']
