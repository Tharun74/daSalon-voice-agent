import asyncio
import base64
import json
import httpx
import pytest
from app.voice import stt, tts
from app.voice.session import pcm_wav
from app.voice.formatter import SentenceChunker


def test_provider_wire_contracts_and_failure(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.host == 'api.sarvam.ai':
            if request.url.path == '/speech-to-text':
                return httpx.Response(200, json={'transcript': 'Hello from Sarvam', 'language_code': 'hi-IN'})
            return httpx.Response(200, json={'audios': [base64.b64encode(b'RIFFtest').decode()]})
        return httpx.Response(200, json={'text': 'Hello', 'duration': 1.2, 'segments': []})
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(stt.config, 'FIREWORKS_API_KEY', 'test-only')
    monkeypatch.setenv('SARVAM_API_KEY', 'test-only')
    transcript = asyncio.run(stt.FireworksSTT().transcribe(pcm_wav(bytes(3200)), 'audio/wav', 'hi-IN'))
    assert transcript.text == 'Hello'
    assert requests[0].url.path == '/audio/v3-turbo/v1/audio/transcriptions'
    assert requests[0].headers['authorization'] == 'Bearer test-only'
    assert b'name="language"\r\n\r\nhi' in requests[0].content
    transcript_sarvam = asyncio.run(stt.SarvamSTT().transcribe(pcm_wav(bytes(3200)), 'audio/wav', 'hi-IN'))
    assert transcript_sarvam.text == 'Hello from Sarvam'
    sarvam_req = next(r for r in requests if r.url.path == '/speech-to-text')
    assert sarvam_req.headers['api-subscription-key'] == 'test-only'
    audio = asyncio.run(tts.SarvamTTS().synthesize('Hello', 'en-IN', 'priya'))
    assert audio == b'RIFFtest'
    payload = json.loads(requests[-1].content)
    assert payload['language_code'] == 'en-IN' and payload['model'] == 'bulbul:v3'
    assert payload['speech_sample_rate'] == 24000
    assert requests[-1].headers['api-subscription-key'] == 'test-only'
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(**kw, transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    with pytest.raises(stt.BrowserFallback):
        asyncio.run(tts.SarvamTTS().synthesize('Hello', 'en-IN', 'priya'))
    with pytest.raises(stt.BrowserFallback):
        asyncio.run(stt.FireworksSTT().transcribe(b'a', 'audio/wav', 'en-IN'))
    with pytest.raises(stt.BrowserFallback):
        asyncio.run(stt.SarvamSTT().transcribe(b'a', 'audio/wav', 'en-IN'))


def test_currency_abbreviation_does_not_split_sentence():
    c = SentenceChunker()
    assert c.feed('It costs Rs. ') == []
    assert c.feed('1,200. Next') == ['It costs Rs. 1,200.']
