"""Opt-in local integration check using configured provider credentials."""
import asyncio
import json
import uuid
from websockets.asyncio.client import connect

async def main():
    session = str(uuid.uuid4())
    async with connect(f'ws://127.0.0.1:8001/voice/ws?salon_id=glow-studio&session_id={session}',
            origin='http://127.0.0.1:3000',max_size=2**22) as ws:
        sent = False
        response_started = False
        audio_chunks = 0
        reply = ''
        async with asyncio.timeout(60):
            async for raw in ws:
                if not isinstance(raw,str): continue
                event = json.loads(raw)
                if event.get('type') == 'error': raise RuntimeError(event.get('message'))
                if event.get('type') == 'state' and not sent:
                    sent = True
                    await ws.send(json.dumps({'type':'text','text':'What is the price and duration of the Signature Haircut & Blowdry?'}))
                if event.get('type') == 'final_transcript': response_started = True
                if response_started and event.get('type') == 'assistant_text': reply = event.get('text','')
                if response_started and event.get('type') == 'audio_chunk': audio_chunks += 1
                if response_started and event.get('type') == 'audio_end': break
        assert reply and '<|channel|>' not in reply and audio_chunks > 0
        print(json.dumps({'reply':reply,'audio_chunks':audio_chunks,'streaming_audio':'passed'}))

asyncio.run(main())
