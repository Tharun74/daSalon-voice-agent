"""Sarvam native streaming transports. Keys never cross the application boundary."""
import asyncio
import base64
import json
import os
from urllib.parse import urlencode
from websockets.asyncio.client import connect
from app.voice.sarvam_config import speech_profile

async def socket(path, query):
    key = os.environ.get('SARVAM_API_KEY')
    if not key:
        raise RuntimeError('Configure SARVAM_API_KEY for live calls')
    return await connect('wss://api.sarvam.ai/' + path + '?' + urlencode(query),
        additional_headers={'Api-Subscription-Key': key}, open_timeout=10,
        ping_interval=15, ping_timeout=10, max_size=2**22)

class LiveSTT:
    async def open(self):
        self.ws = await socket('speech-to-text-realtime/ws', {
            'model': os.getenv('SARVAM_REALTIME_MODEL', 'saaras:v4'),
            'language_code': 'auto', 'mode': 'codemix', 'stream_type': 'fast',
            'encoding': 'linear16', 'sample_rate': 16000, 'endpointing': 'vad',
            'silence_duration_ms': 300, 'min_speech_duration_ms': 160,
            'return_timestamps': 'true'})
        return self

    async def audio(self, pcm):
        await self.ws.send(json.dumps({'event': 'audio_input', 'audio': base64.b64encode(pcm).decode()}))

    async def events(self):
        async for raw in self.ws:
            event = json.loads(raw)
            if event.get('event') == 'error':
                raise RuntimeError('Sarvam transcription failed')
            yield event

    async def close(self):
        if getattr(self, 'ws', None):
            await self.ws.close()

class LiveTTS:
    """One warm socket per call; close on cancellation to discard stale audio."""
    def __init__(self, cfg):
        self.cfg = cfg.model_copy(deep=True)
        self.ws = None
        self.model = None

    async def open(self, language=None):
        model, _ = speech_profile(self.cfg.voice_id, language or self.cfg.language_default)
        if self.ws is not None and self.model != model:
            await self.close()
        if self.ws is None:
            self.ws = await socket('text-to-speech/ws', {'model': model, 'send_completion_event': 'true'})
            self.model = model
        return self

    async def stream(self, text, language):
        await self.open(language)
        _, voice = speech_profile(self.cfg.voice_id, language)
        await self.ws.send(json.dumps({'type': 'config', 'data': {
            'speaker': voice, 'language_code': language,
            'pace': self.cfg.pace, 'speech_sample_rate': 24000,
            'enable_preprocessing': True,
            'output_audio_codec': 'linear16'}}))
        await self.ws.send(json.dumps({'type': 'text', 'data': {'text': text}}))
        await self.ws.send(json.dumps({'type': 'flush'}))
        try:
            while True:
                event = json.loads(await asyncio.wait_for(self.ws.recv(), 15))
                if event.get('type') == 'audio':
                    data = event['data']
                    if data['content_type'] not in ('audio/pcm', 'audio/linear16', 'audio/raw'):
                        raise RuntimeError('Unexpected Sarvam audio format')
                    yield base64.b64decode(data['audio'])
                elif event.get('type') == 'error':
                    raise RuntimeError('Sarvam speech generation failed')
                elif event.get('type') == 'event' and event.get('data', {}).get('event_type') == 'final':
                    break
        except BaseException:
            await self.close()
            raise

    async def close(self):
        ws, self.ws = self.ws, None
        if ws is not None:
            await ws.close()
