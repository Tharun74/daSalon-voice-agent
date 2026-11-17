"""Shared model/persona selection for previews, live speech, and audio caches.

Persona IDs: https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices
Keep v3 for Malayalam/Odia until v4 has language-matched personas.
"""
import os

V4_MODEL = 'bulbul:v4-flash'
V4_DEFAULT = 'simran_en_customer'
V4_LANGUAGE_VOICES = {
    'hi-IN': 'simran_enhi_customer',
    'ta-IN': 'gokul_ta_narration',
    'te-IN': 'kavitha_te_conversation',
    'kn-IN': 'chaitra_kn_conversation',
    'mr-IN': 'ishita_mr_conversational',
    'bn-IN': 'roopa_bn_conversational',
    'gu-IN': 'pooja_gu_customer',
    'pa-IN': 'anand_pa_customer',
}


def speech_profile(voice, language):
    model = os.getenv('TTS_MODEL', V4_MODEL)
    if model not in (V4_MODEL, 'bulbul:v3'):
        raise ValueError('TTS_MODEL must be bulbul:v4-flash or bulbul:v3')
    if model == 'bulbul:v3' or language in ('ml-IN', 'od-IN'):
        return 'bulbul:v3', voice
    if language == 'en-IN':
        # Existing salon settings store v3 names; never send these names to v4.
        return model, {
            'neha': 'neha_en_customer', 'ishita': 'ishita_en_customer',
            'rahul': 'dev_en_conversational', 'shubh': 'shubh_enhi_companion',
        }.get(voice, V4_DEFAULT)
    return model, V4_LANGUAGE_VOICES.get(language, V4_DEFAULT)
