import asyncio
import json
import os
import threading
import time
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.chat import run_turn_stream
from app.service_browsing import is_menu_request
from app.voice import stt, tts
from app.voice.formatter import SentenceChunker, speakable, language_for
from app.voice.session import (validate_session, reserve, limit, EndpointDetector,
    pcm_wav, record_usage, IDLE_SECONDS, SESSION_SECONDS)

router = APIRouter()

_filler_cache: dict[str, bytes] = {}  # pre-synthesized filler audio keyed by text+lang


def next_event(iterator):
    return next(iterator, None)


@router.websocket("/voice/ws")
async def voice_socket(ws: WebSocket):
    origins = os.getenv("VOICE_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if ws.headers.get("origin") not in origins:
        await ws.close(code=1008)
        return
    if os.getenv("STT_PROVIDER") != "fake":
        from app.voice.live import live_call
        return await live_call(ws)
    salon_id = ws.query_params.get("salon_id", "")
    session_id = ws.query_params.get("session_id") or str(uuid.uuid4())
    task, cancel = None, threading.Event()
    try:
        validate_session(salon_id, session_id)
        with reserve(salon_id, session_id):
            await ws.accept()
            await ws.send_json({"type": "state", "state": "idle", "session_id": session_id,
                "audio_format": "audio/wav", "sample_rate": 24000,
                "input_format": "pcm_s16le", "input_sample_rate": 16000,
                "streaming_stt": False})
            detector = EndpointDetector()
            started = last_activity = time.monotonic()
            last_speech = 0
            generation = 0

            async def interrupt():
                nonlocal task, cancel, generation
                cancel.set()
                generation += 1
                if task:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                task = None
                cancel = threading.Event()
                await ws.send_json({"type": "state", "state": "listening", "interrupted": True, "generation": generation})

            async def respond(text, pcm, token, gen):
                cfg = validate_session(salon_id, session_id)
                turn_start = time.perf_counter()
                turn_id = str(uuid.uuid4())
                metrics = {"stt_ms": 0, "llm_first_token_ms": None, "tts_first_byte_ms": None}
                seconds, chars, first_audio = 0, 0, None
                async def send(event):
                    if not token.is_set():
                        await ws.send_json({**event, "generation": gen})
                async def say(sentence):
                    nonlocal chars, first_audio
                    speech = speakable(sentence)
                    if not speech or token.is_set():
                        return
                    lang = language_for(sentence, cfg.language_default)
                    tts_start = time.perf_counter()
                    try:
                        # Use pre-cached audio for known filler phrases to skip network round-trip.
                        cache_key = speech + "|" + lang
                        cached = _filler_cache.get(cache_key) or _filler_cache.get(speech)
                        if cached is not None:
                            audio = cached
                        else:
                            audio = await tts.get_tts(cfg).synthesize(speech, lang, cfg.voice_id, cfg.pace)
                        if token.is_set():
                            return
                        if metrics["tts_first_byte_ms"] is None:
                            metrics["tts_first_byte_ms"] = round((time.perf_counter() - tts_start) * 1000)
                        if first_audio is None:
                            first_audio = round((time.perf_counter() - turn_start) * 1000)
                        chars += len(speech)
                        await send({"type": "state", "state": "speaking"})
                        await ws.send_bytes(audio)
                    except stt.BrowserFallback:
                        await send({"type": "speech", "text": speech, "language": lang, "pace": cfg.pace})
                try:
                    await send({"type": "state", "state": "thinking"})
                    if pcm:
                        seconds = len(pcm) / 32000
                        transcript = await stt.get_stt().transcribe(pcm_wav(pcm), "audio/wav", cfg.language_default)
                        text = transcript.text
                        if transcript.confidence is not None and transcript.confidence < .5:
                            await send({"type": "error", "message": "I could not hear clearly. Please repeat."})
                            return
                        metrics["stt_ms"] = round((time.perf_counter() - turn_start) * 1000)
                    if not text or not text.strip() or len(text) > 2000:
                        await send({"type": "error", "message": "Please repeat a shorter message."})
                        return
                    await send({"type": "final_transcript", "text": text})
                    iterator = run_turn_stream(salon_id, session_id, text, cancel=token, turn_id=turn_id)
                    chunker = SentenceChunker()
                    spoken = ""
                    llm_start = time.perf_counter()
                    tool_wait = False
                    filler_sent = False
                    result = None
                    while not token.is_set():
                        pending = asyncio.create_task(asyncio.to_thread(next_event, iterator))
                        if tool_wait and cfg.filler_enabled and not filler_sent and not is_menu_request(text):
                            try:
                                event = await asyncio.wait_for(asyncio.shield(pending), timeout=1)
                            except asyncio.TimeoutError:
                                filler_sent = True
                                await say(cfg.filler_text)
                                event = await pending
                        else:
                            event = await pending
                        if event is None:
                            break
                        if event["type"] == "assistant_text_delta":
                            if metrics["llm_first_token_ms"] is None:
                                metrics["llm_first_token_ms"] = round((time.perf_counter()-llm_start)*1000)
                            await send(event)
                            for sentence in chunker.feed(event["text"]):
                                spoken += sentence
                                await say(sentence)
                        elif event["type"] == "tool_event":
                            tool_wait = event["phase"] == "start"
                            # No internal tool names or arguments in customer events.
                            await send({"type": "tool_event", "phase": event["phase"]})
                        elif event["type"] == "result":
                            result = event["result"]
                            for sentence in chunker.feed("", final=True):
                                spoken += sentence
                                await say(sentence)
                            if not spoken or result["reply"] != spoken:
                                # Deterministic booking read-back or handoff/error reply.
                                if not spoken or "Shall I book" in result["reply"] or "क्या मैं बुक" in result["reply"]:
                                    await say(result["reply"])
                            await send({"type": "assistant_text", "text": result["reply"]})
                            if result.get("status") == "handed_off":
                                await send({"type": "handoff"})
                    metrics["total_ms"] = round((time.perf_counter()-turn_start)*1000)
                    metrics["first_audio_ms"] = first_audio
                    await send({"type": "timings", **metrics})
                except stt.BrowserFallback:
                    await send({"type": "error", "fallback": "browser_stt", "message": "Please repeat using browser recognition, or switch to text."})
                except asyncio.CancelledError:
                    token.set()
                    raise
                except Exception:
                    await send({"type": "error", "message": "Voice connection failed. Please try again or switch to text."})
                finally:
                    record_usage(salon_id, session_id, seconds, chars, metrics, turn_id)
                    if not token.is_set():
                        await send({"type": "state", "state": "listening"})

            async def begin(text=None, pcm=None):
                nonlocal task
                limit(salon_id, session_id, ws.client.host)
                await interrupt()
                task = asyncio.create_task(respond(text, pcm, cancel, generation))

            while True:
                remaining = min(IDLE_SECONDS - (time.monotonic()-last_activity), SESSION_SECONDS - (time.monotonic()-started))
                if remaining <= 0:
                    await ws.close(code=1000, reason="Voice session timed out")
                    break
                message = await asyncio.wait_for(ws.receive(), timeout=remaining)
                if message["type"] == "websocket.disconnect":
                    break
                validate_session(salon_id, session_id)
                if message.get("bytes") is not None:
                    speaking, utterance = detector.feed(message["bytes"])
                    if speaking:
                        last_activity = time.monotonic()
                        # Require sustained speech to avoid transient noise interrupts.
                        if detector.speech_ms >= 160 and last_speech == 0:
                            last_speech = time.monotonic()
                            if task and not task.done():
                                await interrupt()
                    if utterance:
                        last_speech = 0
                        await begin(pcm=utterance)
                elif message.get("text"):
                    if len(message["text"]) > 8192:
                        raise HTTPException(413, "Control too large")
                    control = json.loads(message["text"])
                    if not isinstance(control, dict):
                        raise HTTPException(422, "Invalid control")
                    if control.get("salon_id", salon_id) != salon_id or control.get("session_id", session_id) != session_id:
                        raise HTTPException(403, "Session tenant cannot change")
                    kind = control.get("type")
                    last_activity = time.monotonic()
                    if kind == "text":
                        text = control.get("text")
                        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
                            raise HTTPException(422, "Invalid transcript")
                        await begin(text=text)
                    elif kind == "interrupt":
                        await interrupt()
                    elif kind == "start":
                        detector = EndpointDetector()
                        await ws.send_json({"type": "state", "state": "listening"})
                    elif kind == "stop":
                        if detector.buffer:
                            pcm = bytes(detector.buffer)
                            detector = EndpointDetector()
                            await begin(pcm=pcm)
                    else:
                        raise HTTPException(422, "Unknown voice control")
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await ws.close(code=1000, reason="Voice session timed out")
    except (HTTPException, ValueError, TypeError) as exc:
        try:
            await ws.send_json({"type": "error", "message": getattr(exc, "detail", "Invalid voice request")})
            await ws.close(code=1008)
        except RuntimeError:
            pass
    finally:
        cancel.set()
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
