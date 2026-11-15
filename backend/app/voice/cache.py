"""Fixed audio cache: settings are part of the key, so calls never change speaker."""
import hashlib
import io
from pathlib import Path
import wave
ROOT = Path(__file__).resolve().parents[2] / 'data' / 'voice-cache'

def cache_path(cfg, text, language):
    key = f'bulbul:v3|{cfg.voice_id}|{cfg.pace}|{language}|{text}'
    return ROOT / (hashlib.sha256(key.encode()).hexdigest() + '.wav')

def cached_pcm(cfg, text, language):
    path = cache_path(cfg, text, language)
    if not path.exists():
        return None
    with wave.open(io.BytesIO(path.read_bytes()), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            return None
        return wav.readframes(wav.getnframes())
