"""Exercise live orchestration, including the timer which can inject filler."""
import asyncio
from contextlib import nullcontext
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from app.service_browsing import MENU_REPLY
from app.voice.live import live_call
from app.voice.settings import VoiceSettings


class MenuVoiceIntegrationTests(unittest.TestCase):
    def test_slow_service_reply_never_synthesizes_filler(self):
        spoken = []

        class STT:
            async def open(self): pass
            async def close(self): pass
            async def events(self):
                await asyncio.sleep(3600)
                yield {}

        class TTS:
            def __init__(self, cfg): pass
            async def open(self): pass
            async def close(self): pass
            async def stream(self, text, lang):
                spoken.append(text)
                yield b'\x00\x00'

        def slow_turn(*args, **kwargs):
            time.sleep(.8)  # Longer than the .6-second automatic filler threshold.
            yield {'type': 'result', 'result': {'reply': MENU_REPLY}}

        app = FastAPI()
        @app.websocket('/test')
        async def endpoint(ws: WebSocket):
            await live_call(ws)
        cfg = VoiceSettings(greeting='Hello.', filler_text='One moment, checking that for you.')
        with patch('app.voice.live.LiveSTT', STT), patch('app.voice.live.LiveTTS', TTS), \
             patch('app.voice.live.validate_session', return_value=cfg), \
             patch('app.voice.live.reserve', return_value=nullcontext()), \
             patch('app.voice.live.run_turn_stream', slow_turn), \
             patch('app.voice.cache.cached_pcm', return_value=None):
            with TestClient(app).websocket_connect('/test?salon_id=glow-studio&session_id=test') as ws:
                while ws.receive_json()['type'] != 'audio_end': pass
                spoken.clear()
                ws.send_json({'type': 'text', 'text': 'What services do you offer?'})
                while ws.receive_json()['type'] != 'audio_end': pass
                self.assertEqual(spoken, [MENU_REPLY])
