"""Fresh local demo data only; never overwrites saved settings on startup."""
from datetime import datetime, timedelta
from app.db import get_db, persist_mock_data
from app.seed import seed_database

def ensure_demo():
    db = get_db()
    if db.salons.find_one({'_id': 'glow-studio'}):
        return
    seed_database()
    db.bot_configs.update_one({'salon_id': 'glow-studio'}, {'$set': {
        'tone': 'Warm, calm and concise. Natural spoken language, no emojis.',
        'instructions': 'This is Glow Studio, an illustrative salon demo. Help with services, prices, approved aftercare and bookings. Ask one question at a time. A first-time colour service needs a patch-test consultation. Never invent treatment guidance.',
        'languages': ['English', 'Hindi', 'Tamil'],
        'enabled_tools': ['get_services', 'get_staff', 'get_offers', 'get_hours', 'check_availability', 'book_appointment', 'log_unanswered_question'],
    }})
    db.offers.update_many({'salon_id': 'glow-studio'}, {'$set': {'valid_until': (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')}})
    persist_mock_data()
