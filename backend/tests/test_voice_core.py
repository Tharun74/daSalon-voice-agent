import asyncio
from types import SimpleNamespace
import pytest
from app.voice.formatter import speakable, language_for, SentenceChunker
from app.voice.confirmation import prepare_booking
from app.voice.settings import VoiceSettings
from app.voice import stt, tts
from app.voice.session import EndpointDetector, pcm_wav, validate_audio


def test_formatter():
    assert speakable('**Rs 1,200** at 11:00 😊 [book](https://example.com)') == 'twelve hundred rupees at eleven AM book'
    assert speakable('₹500 at 14:05, 30 mins') == 'five hundred rupees at two oh five PM, 30 minutes'
    assert 'http' not in speakable('visit https://example.com')


def test_chunker_and_language():
    c = SentenceChunker()
    assert c.feed('Hello') == []
    assert c.feed(' there. Next') == ['Hello there.']
    assert c.feed(' sentence', final=True) == ['Next sentence']
    assert language_for('नमस्ते') == 'hi-IN'
    assert language_for('Aap kaise hain?') == 'hi-IN'
    assert language_for('Hello', 'hi-IN') == 'en-IN'
    assert language_for('வணக்கம்') == 'ta-IN'


def test_confirmation_exact_and_expiring():
    args = dict(customer_name='Priya', phone='9876543210', service_name='Haircut', start_time='2027-12-10T11:00')
    ok, pending, reply = prepare_booking(args, None, 'yes')
    assert not ok and '9 8 7 6 5 4 3 2 1 0' in reply
    assert prepare_booking(args, pending, 'yes')[0]
    assert not prepare_booking({**args, 'phone':'123'}, pending, 'yes')[0]
    assert not prepare_booking(args, {**pending, 'expires':0}, 'yes')[0]
    assert not prepare_booking(args, pending, 'yes but change time')[0]


def test_defaults_and_provider_selection(monkeypatch):
    assert VoiceSettings().enabled
    monkeypatch.setattr(stt.config, 'FIREWORKS_API_KEY', '')
    monkeypatch.delenv('SARVAM_API_KEY', raising=False)
    assert type(stt.get_stt()) is stt.BrowserSTT
    assert type(tts.get_tts()) is tts.BrowserTTS
    monkeypatch.setenv('STT_PROVIDER','fake')
    monkeypatch.setenv('TTS_PROVIDER','fake')
    assert asyncio.run(stt.get_stt().transcribe(b'a','audio/wav','en-IN')).text
    assert asyncio.run(tts.get_tts().synthesize('Hello','en-IN','priya')).startswith(b'RIFF')


def test_endpointing_limits():
    d = EndpointDetector()
    loud = b'\x00\x20' * 3200
    assert d.feed(loud)[0]
    assert d.feed(bytes(24000))[1] is not None
    assert validate_audio(pcm_wav(loud)) == .2
    with pytest.raises(Exception):
        validate_audio(pcm_wav(bytes(16000*2*31)))
