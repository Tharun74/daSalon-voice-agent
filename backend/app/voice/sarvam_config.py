"""Shared model/persona selection for previews, live speech, and audio caches.

Persona IDs: https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices
Keep v3 for Malayalam/Odia until v4 has language-matched personas.
"""
import os

V4_MODEL = 'bulbul:v4-flash'
V4_DEFAULT = 'simran_en_customer'
V4_VOICES = {
    'simran_en_customer': 'Simran · English · customer care',
    'simran_enhi_customer': 'Simran · Hindi + English · customer care',
    'neha_en_customer': 'Neha · English · customer care',
    'ishita_en_customer': 'Ishita · English · customer care',
    'ritu_hi_customer_warm': 'Ritu · Hindi · warm customer care',
    'kavya_hi_conversational': 'Kavya · Hindi · conversation',
    'shreya_hi_conversational': 'Shreya · Hindi · conversation',
    'dev_en_conversational': 'Dev · English · conversation',
    'shubh_enhi_companion': 'Shubh · Hindi + English · companion',
    'gokul_ta_narration': 'Gokul · Tamil · narration (male)',
    'kavitha_te_conversation': 'Kavitha · Telugu · conversation',
    'chaitra_kn_conversation': 'Chaitra · Kannada · conversation',
    'ishita_mr_conversational': 'Ishita · Marathi · conversation',
    'roopa_bn_conversational': 'Roopa · Bengali · conversation',
    'pooja_gu_customer': 'Pooja · Gujarati · customer care',
    'anand_pa_customer': 'Anand · Punjabi · customer care (male)',
}
LEGACY_V4_VOICES = {
    'simran': V4_DEFAULT, 'priya': V4_DEFAULT,
    'neha': 'neha_en_customer', 'ishita': 'ishita_en_customer',
    'ritu': 'ritu_hi_customer_warm', 'kavya': 'kavya_hi_conversational',
    'shreya': 'shreya_hi_conversational', 'rahul': 'dev_en_conversational',
    'shubh': 'shubh_enhi_companion',
}


def speech_profile(voice, language, settings=None):
    model = os.getenv('TTS_MODEL', V4_MODEL)
    if model not in (V4_MODEL, 'bulbul:v3'):
        raise ValueError('TTS_MODEL must be bulbul:v4-flash or bulbul:v3')
    if model == 'bulbul:v3' or language in ('ml-IN', 'od-IN'):
        return 'bulbul:v3', voice
    base_voice = getattr(settings, 'v4_voice_id', None) or LEGACY_V4_VOICES.get(voice, V4_DEFAULT)
    overrides = getattr(settings, 'v4_language_voices', {})
    # Changing language alone must never change the salon's chosen persona.
    return model, overrides.get(language, base_voice)


def profile_for(settings, language):
    return speech_profile(settings.voice_id, language, settings)
