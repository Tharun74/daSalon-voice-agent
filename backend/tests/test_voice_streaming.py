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
    monkeypatch.setenv('TTS_MODEL', 'bulbul:v4-flash')
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
        cfg=VoiceSettings(voice_id='priya');tts=await LiveTTS(cfg).open();cfg.v4_voice_id='dev_en_conversational'
        stream=tts.stream('Hello','ta-IN')
        assert len(await anext(stream))==640
        assert queries[1]['model']=='bulbul:v4-flash'
        assert sockets[1].sent[0]['data']['speaker']=='simran_en_customer'
        assert sockets[1].sent[0]['data']['language_code']=='ta-IN'
        assert sockets[1].sent[0]['data']['enable_preprocessing'] is True
        assert sockets[1].sent[0]['data']['speech_sample_rate']==24000
        await stream.aclose()
        assert sockets[1].closed
        await stt.close()
    asyncio.run(check())


def test_v4_profiles_and_cache_isolation(monkeypatch):
    from app.voice.sarvam_config import speech_profile
    from app.voice.cache import cache_path
    from app.voice.formatter import speakable
    monkeypatch.setenv('TTS_MODEL', 'bulbul:v4-flash')
    assert speech_profile('priya','en-IN') == ('bulbul:v4-flash','simran_en_customer')
    assert speech_profile('priya','hi-IN') == ('bulbul:v4-flash','simran_en_customer')
    assert speech_profile('priya','ml-IN') == ('bulbul:v3','priya')
    assert speech_profile('priya','od-IN') == ('bulbul:v3','priya')
    cfg=VoiceSettings(voice_id='priya')
    v4=cache_path(cfg,'Welcome','en-IN')
    monkeypatch.setenv('TTS_MODEL','bulbul:v3')
    assert cache_path(cfg,'Welcome','en-IN') != v4
    assert speech_profile('priya','en-IN') == ('bulbul:v3','priya')
    # v4 normalizes currency and times in the target language, not English.
    assert speakable('**₹1,200** at 14:05, 45 mins', normalize_numbers=False) == '₹1,200 at 14:05, 45 minutes'


def test_persona_stays_fixed_unless_owner_overrides(monkeypatch):
    from pydantic import ValidationError
    from app.voice.sarvam_config import profile_for
    from app.voice.cache import cache_path
    monkeypatch.setenv('TTS_MODEL','bulbul:v4-flash')
    cfg=VoiceSettings(voice_id='priya',v4_voice_id='neha_en_customer')
    for language in ['en-IN','ta-IN','hi-IN','te-IN']:
        assert profile_for(cfg,language)==('bulbul:v4-flash','neha_en_customer')
    before=cache_path(cfg,'Hello','ta-IN')
    cfg.v4_language_voices={'ta-IN':'gokul_ta_narration'}
    saved=VoiceSettings.model_validate(cfg.model_dump())
    assert profile_for(saved,'ta-IN')==('bulbul:v4-flash','gokul_ta_narration')
    assert profile_for(saved,'en-IN')==('bulbul:v4-flash','neha_en_customer')
    assert cache_path(saved,'Hello','ta-IN')!=before
    assert profile_for(saved,'ml-IN')==('bulbul:v3','priya')
    with pytest.raises(ValidationError):VoiceSettings(v4_voice_id='invented_voice')
    with pytest.raises(ValidationError):VoiceSettings(v4_language_voices={'ta-IN':'priya'})
    with pytest.raises(ValidationError):VoiceSettings(v4_language_voices={'ml-IN':'neha_en_customer'})


def test_live_audio_starts_before_long_reply_finishes(monkeypatch):
    import threading
    from fastapi.testclient import TestClient
    from app.main import app
    from app.voice import live
    audio_started=threading.Event()
    started_before_result=[]
    text=('Our signature smoothing treatment gently softens frizz and adds a glossy finish '
          'while your stylist tailors the treatment to your hair type and explains the care '
          'routine so you can keep the result looking smooth and healthy between visits')
    class STT:
        async def open(self):return self
        async def events(self):
            await asyncio.Event().wait()
            yield {}
        async def close(self):pass
    class TTS:
        def __init__(self,cfg):pass
        async def open(self):return self
        async def stream(self,speech,language):
            if speech.startswith('Our signature'):audio_started.set()
            yield bytes(480)
        async def close(self):pass
    def turns(*args,**kwargs):
        yield {'type':'assistant_text_delta','text':text}
        started_before_result.append(audio_started.wait(2))
        yield {'type':'result','result':{'reply':text,'status':'active'}}
    monkeypatch.setenv('STT_PROVIDER','sarvam')
    monkeypatch.setenv('VOICE_ALLOWED_ORIGINS','http://localhost:3000')
    monkeypatch.setattr(live,'LiveSTT',STT)
    monkeypatch.setattr(live,'LiveTTS',TTS)
    monkeypatch.setattr(live,'run_turn_stream',turns)
    with TestClient(app).websocket_connect('/voice/ws?salon_id=glow-studio&session_id=bounded-first-audio',headers={'origin':'http://localhost:3000'}) as ws:
        def until_end():
            while True:
                e=ws.receive_json()
                assert e['type']!='error',e
                if e['type']=='audio_end':return
        until_end()
        ws.send_json({'type':'text','text':'Tell me about smoothing'})
        until_end()
        ws.close()
        while ws.receive()['type']!='websocket.close':
            pass
    assert started_before_result==[True]


def test_live_chunker_prefers_clauses_without_splitting_prices():
    from app.voice.formatter import SentenceChunker
    chunker=SentenceChunker(limit=220,prefer_clauses=True)
    text='This treatment costs ₹1,200 and takes 45 minutes, '+('it gently improves the texture of your hair '*2)
    chunks=chunker.feed(text)
    assert chunks[0]=='This treatment costs ₹1,200 and takes 45 minutes,'
    assert ' '.join(chunks+chunker.feed('',final=True))==text.strip()


def test_owner_persona_settings_round_trip(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    monkeypatch.setenv('VOICE_ADMIN_TOKEN','test-owner')
    client=TestClient(app)
    path='/salons/glow-studio/bot-config'
    headers={'Authorization':'Bearer test-owner'}
    original=get_db().bot_configs.find_one({'salon_id':'glow-studio'})['voice']
    try:
        loaded=client.get(path,headers=headers).json()
        assert loaded['voice']['v4_voice_id']
        assert 'neha_en_customer' in loaded['voice_options']
        voice={**loaded['voice'],'v4_voice_id':'neha_en_customer',
               'v4_language_voices':{'hi-IN':'simran_enhi_customer'}}
        assert client.put(path,json={'voice':voice}).status_code==401
        assert client.put(path,headers=headers,json={'voice':voice}).status_code==200
        saved=client.get(path,headers=headers).json()['voice']
        assert saved['v4_voice_id']=='neha_en_customer'
        assert saved['v4_language_voices']=={'hi-IN':'simran_enhi_customer'}
        assert client.put(path,headers=headers,json={'voice':{**voice,'v4_voice_id':'invalid'}}).status_code==422
    finally:
        get_db().bot_configs.update_one({'salon_id':'glow-studio'},{'$set':{'voice':original}})


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
