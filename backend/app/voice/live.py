"""Continuous call orchestration with independently streaming recognition and playback."""
import asyncio
import base64
import json
import logging
import os
import re
import threading
import time
import uuid
from fastapi import HTTPException, WebSocketDisconnect
from app.chat import run_turn_stream
from app.voice.streaming import LiveSTT, LiveTTS
from app.voice.formatter import SentenceChunker, speakable, language_for
from app.voice.session import validate_session, reserve, limit, record_usage, IDLE_SECONDS, SESSION_SECONDS

log = logging.getLogger('dasalon.voice.live')
# Only suppress acknowledgments during an active reply, never answers while listening.
BACKCHANNELS = {'hmm', 'hm', 'mm', 'mmm', 'okay', 'ok', 'uh huh'}

def is_backchannel(text):
    return re.sub(r'[^\w\s]', '', text.lower()).strip() in BACKCHANNELS

async def live_call(ws):
    salon = ws.query_params.get('salon_id', '')
    session = ws.query_params.get('session_id') or str(uuid.uuid4())
    task = reader = None
    cancel = threading.Event()
    recognizer, speaker = LiveSTT(), None
    browser_gaps = {}
    input_bytes = 0
    generation, last_voice, last_activity = 0, None, time.perf_counter()
    active_audio, overlapping, language = False, False, 'en-IN'
    started = time.perf_counter()
    try:
        cfg = validate_session(salon, session).model_copy(deep=True)
        speaker = LiveTTS(cfg)
        language = cfg.language_default
        with reserve(salon, session):
            await ws.accept()
            await asyncio.gather(recognizer.open(), speaker.open())
            await ws.send_json({'type': 'state', 'state': 'listening', 'streaming_stt': True,
                                'audio_format': 'pcm_s16le', 'sample_rate': 24000, 'session_id': session})

            async def interrupt():
                nonlocal task, cancel, generation, active_audio
                cancel.set()
                generation += 1
                if task:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                task = None
                active_audio = False
                cancel = threading.Event()
                await ws.send_json({'type': 'state', 'state': 'listening', 'interrupted': True, 'generation': generation})

            async def respond(text, token, gen, ended, stt_ms=0, greeting=False):
                nonlocal active_audio
                turn_id = str(uuid.uuid4())
                metrics = {'stt_ms': stt_ms, 'llm_first_token_ms': None,
                           'tts_first_byte_ms': None, 'first_audio_ms': None,
                           'endpoint': 'server_energy_last_voiced_frame', 'generation': gen}
                sentences = asyncio.Queue(maxsize=4)
                chars = 0
                async def send(event):
                    if not token.is_set():
                        await ws.send_json({**event, 'generation': gen, 'turn_id': turn_id})
                async def audio_worker():
                    nonlocal chars, active_audio
                    while True:
                        sentence = await sentences.get()
                        if sentence is None:
                            return
                        speech = speakable(sentence)
                        if not speech:
                            continue
                        lang = language_for(sentence, language)
                        t0 = time.perf_counter()
                        from app.voice.cache import cached_pcm
                        cached = cached_pcm(cfg, speech, lang)
                        async def chunks():
                            if cached is not None:
                                yield cached
                            else:
                                async for chunk in speaker.stream(speech, lang):
                                    yield chunk
                        async for pcm in chunks():
                            if token.is_set():
                                return
                            now = time.perf_counter()
                            if metrics['tts_first_byte_ms'] is None:
                                metrics['tts_first_byte_ms'] = round((now-t0)*1000)
                            if metrics['first_audio_ms'] is None:
                                metrics['first_audio_ms'] = round((now-ended)*1000)
                            active_audio = True
                            await send({'type': 'audio_chunk', 'audio': base64.b64encode(pcm).decode(),
                                        'sample_rate': 24000})
                        chars += len(speech)
                worker = asyncio.create_task(audio_worker())
                try:
                    if greeting:
                        await send({'type': 'assistant_text', 'text': text})
                        await sentences.put(text)
                    else:
                        await send({'type': 'final_transcript', 'text': text})
                        iterator = run_turn_stream(salon, session, text, cancel=token, turn_id=turn_id)
                        chunker = SentenceChunker()
                        spoken, tool_wait, filler_sent = '', False, False
                        llm_start = time.perf_counter()
                        while not token.is_set():
                            pending = asyncio.create_task(asyncio.to_thread(next, iterator, None))
                            try:
                                if tool_wait and cfg.filler_enabled and not filler_sent and language == cfg.language_default:
                                    done, _ = await asyncio.wait({pending}, timeout=.25)
                                    if not done:
                                        filler_sent = True
                                        await sentences.put(cfg.filler_text)
                                event = await pending
                            finally:
                                # The cancellation flag prevents the shared brain executing later tools.
                                if token.is_set():
                                    pending.cancel()
                            if event is None:
                                break
                            if worker.done():
                                await worker  # Surface provider failures without filling a dead queue.
                            if event['type'] == 'assistant_text_delta':
                                if metrics['llm_first_token_ms'] is None:
                                    metrics['llm_first_token_ms'] = round((time.perf_counter()-llm_start)*1000)
                                await send(event)
                                for sentence in chunker.feed(event['text']):
                                    spoken += sentence
                                    await sentences.put(sentence)
                            elif event['type'] == 'tool_event':
                                tool_wait = event['phase'] == 'start'
                            elif event['type'] == 'result':
                                result = event['result']
                                for sentence in chunker.feed('', final=True):
                                    spoken += sentence
                                    await sentences.put(sentence)
                                if not spoken or 'Shall I book' in result['reply'] or 'क्या मैं बुक' in result['reply']:
                                    await sentences.put(result['reply'])
                                await send({'type': 'assistant_text', 'text': result['reply']})
                    await sentences.put(None)
                    await worker
                    await send({'type': 'audio_end'})
                    metrics['total_ms'] = round((time.perf_counter()-ended)*1000)
                    await send({'type': 'timings', **metrics})
                    log.info('voice_latency %s', json.dumps(metrics))
                except asyncio.CancelledError:
                    token.set()
                    raise
                except Exception:
                    log.exception('Live voice turn failed')
                    await send({'type': 'error', 'message': 'Voice connection failed. Please repeat or type your message.'})
                finally:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
                    if turn_id in browser_gaps:
                        metrics['browser_gap_ms'] = browser_gaps.pop(turn_id)
                    record_usage(salon, session, 0, chars, metrics, turn_id)

            async def begin(text, stt_ms=0):
                nonlocal task
                limit(salon, session, ws.client.host)
                await interrupt()
                task = asyncio.create_task(respond(text, cancel, generation, last_voice or time.perf_counter(), stt_ms))

            async def recognize():
                nonlocal overlapping, language, last_activity
                async for event in recognizer.events():
                    kind = event.get('event')
                    if kind == 'vad.speech_start':
                        overlapping = active_audio
                        await ws.send_json({'type': 'playback_pause'})
                    elif kind == 'transcript.partial':
                        await ws.send_json({'type': 'partial_transcript', 'text': event.get('text', '')})
                    elif kind == 'transcript.final':
                        text = event.get('text', '').strip()
                        last_activity = time.perf_counter()
                        from app.db import get_db
                        pending = get_db().conversations.find_one({'salon_id': salon, 'session_id': session}) or {}
                        acknowledgment = overlapping and is_backchannel(text) and not pending.get('voice_pending_booking')
                        if not text or acknowledgment:
                            await ws.send_json({'type': 'playback_resume'})
                            continue
                        language = event.get('language') or language
                        if language == 'or-IN':
                            language = 'od-IN'
                        await begin(text, round((time.perf_counter()-(last_voice or time.perf_counter()))*1000))
                        overlapping = False

            reader = asyncio.create_task(recognize())
            task = asyncio.create_task(respond(cfg.greeting, cancel, generation, time.perf_counter(), greeting=True))
            while True:
                remaining = min(IDLE_SECONDS-(time.perf_counter()-last_activity), SESSION_SECONDS-(time.perf_counter()-started))
                if remaining <= 0:
                    break
                receiving = asyncio.create_task(ws.receive())
                done, _ = await asyncio.wait({receiving, reader}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                if receiving not in done:
                    receiving.cancel()
                    await asyncio.gather(receiving, return_exceptions=True)
                    if reader in done:
                        await reader
                    break
                message = receiving.result()
                if message['type'] == 'websocket.disconnect':
                    break
                validate_session(salon, session)
                pcm = message.get('bytes')
                if pcm is not None:
                    if len(pcm) > 6400 or len(pcm) % 2:
                        raise HTTPException(413, 'Invalid audio frame')
                    import array
                    samples = array.array('h', pcm)
                    if samples and sum((v/32768)**2 for v in samples)/len(samples) > .0004:
                        last_voice = last_activity = time.perf_counter()
                    input_bytes += len(pcm)
                    await recognizer.audio(pcm)
                elif message.get('text'):
                    if len(message['text']) > 8192:
                        raise HTTPException(413, 'Control too large')
                    control = json.loads(message['text'])
                    if not isinstance(control, dict):
                        raise ValueError('Invalid control')
                    if control.get('salon_id', salon) != salon or control.get('session_id', session) != session:
                        raise HTTPException(403, 'Session tenant cannot change')
                    kind = control.get('type')
                    last_activity = time.perf_counter()
                    if kind == 'text':
                        text = control.get('text')
                        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
                            raise ValueError('Invalid transcript')
                        last_voice = time.perf_counter()
                        await begin(text)
                    elif kind == 'interrupt':
                        await interrupt()
                    elif kind == 'playback_done':
                        active_audio = False
                    elif kind == 'playback_started':
                        gap = control.get('gap_ms')
                        if isinstance(gap, (int, float)) and 0 <= gap <= 120000:
                            browser_gaps[control.get('turn_id')] = gap
                            from app.db import get_db
                            get_db().voice_usage.update_one({'salon_id': salon, 'session_id': session,
                                'turn_id': control.get('turn_id')}, {'$set': {'browser_gap_ms': gap}})
                        log.info('voice_browser_latency %s', json.dumps({k: control.get(k) for k in ('generation', 'gap_ms')}))
                    elif kind not in ('start', 'stop'):
                        raise ValueError('Unknown control')
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception('Live call ended')
        try:
            await ws.send_json({'type': 'error', 'message': 'Live voice unavailable. Please reconnect or use text.'})
        except RuntimeError:
            pass
    finally:
        cancel.set()
        for job in (task, reader):
            if job:
                job.cancel()
        await asyncio.gather(*(job for job in (task, reader) if job), return_exceptions=True)
        if input_bytes:
            record_usage(salon, session, input_bytes / 32000, 0, {'kind': 'stream_input_total'})
        await recognizer.close()
        if speaker:
            await speaker.close()
        try:
            await ws.close()
        except RuntimeError:
            pass
