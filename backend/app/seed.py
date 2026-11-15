import logging
from app.db import get_db, persist_mock_data, create_indexes

logger = logging.getLogger("dasalon.seed")


def seed_database():
    """Idempotently seed the three contrasting salons."""
    db = get_db()
    create_indexes()

    salons_data = [
        {
            "_id": "glow-studio",
            "name": "Glow Studio",
            "type": "Unisex Hair & Beauty Salon",
            "address": "100 Feet Road, Indiranagar, Bengaluru, Karnataka 560038",
            "phone": "+91 98450 12345",
            "hours": {
                "mon": "10:00-20:00",
                "tue": "10:00-20:00",
                "wed": "10:00-20:00",
                "thu": "10:00-20:00",
                "fri": "10:00-20:00",
                "sat": "09:30-20:30",
                "sun": "09:30-20:30",
            },
            "brand": {
                "primary": "#EC4899",
                "accent": "#F472B6",
                "badge": "Warm & Friendly ✨",
            },
        },
        {
            "_id": "serenity-spa",
            "name": "Serenity Luxury Spa",
            "type": "Luxury Wellness & Ayurvedic Spa",
            "address": "Pali Hill, Bandra West, Mumbai, Maharashtra 400050",
            "phone": "+91 98200 54321",
            "hours": {
                "mon": "09:00-21:00",
                "tue": "09:00-21:00",
                "wed": "09:00-21:00",
                "thu": "09:00-21:00",
                "fri": "09:00-21:00",
                "sat": "09:00-21:30",
                "sun": "09:00-21:30",
            },
            "brand": {
                "primary": "#0F766E",
                "accent": "#14B8A6",
                "badge": "Calm & Elegant (No Emojis)",
            },
        },
        {
            "_id": "gentlemans-cut",
            "name": "The Gentleman's Cut",
            "type": "Classic Barbershop & Grooming",
            "address": "80 Feet Road, 4th Block, Koramangala, Bengaluru, Karnataka 560034",
            "phone": "+91 97400 67890",
            "hours": {
                "mon": "closed",
                "tue": "09:00-21:00",
                "wed": "09:00-21:00",
                "thu": "09:00-21:00",
                "fri": "09:00-21:00",
                "sat": "08:30-21:30",
                "sun": "08:30-21:30",
            },
            "brand": {
                "primary": "#B45309",
                "accent": "#D97706",
                "badge": "Max 2 Sentences • English/Hindi",
            },
        },
    ]

    bot_configs_data = [
        {
            "salon_id": "glow-studio",
            "tone": "Warm, welcoming, friendly with occasional tasteful emojis (✨, 💇, 💅). Enthusiastic about helping clients feel beautiful and confident.",
            "instructions": (
                "Always mention that a mandatory 24-hour patch test is required before any first-time hair colouring or chemical service. "
                "Highlight our organic, ammonia-free products. Suggest consulting our senior stylists for bridal inquiries. "
                "Maintain an upbeat, encouraging vibe."
            ),
            "languages": ["English", "Kannada", "Hindi"],
            "enabled_tools": [
                "get_services",
                "get_staff",
                "get_offers",
                "get_hours",
                "check_availability",
                "book_appointment",
                "cancel_appointment",
                "escalate_to_human",
                "log_unanswered_question",
            ],
        },
        {
            "salon_id": "serenity-spa",
            "tone": "Calm, serene, sophisticated, and courteous. Absolutely NO emojis under any circumstances. Speak with refined grace and tranquility.",
            "instructions": (
                "Strictly require guests to arrive 15 minutes before their scheduled time for herbal infusion and consultation. "
                "Never diagnose any skin or medical condition; if a guest mentions pain, allergies, or pregnancy, escalate to human concierge. "
                "Highlight our Couples Spa Ritual and organic botanical essential oils."
            ),
            "languages": ["English"],
            "enabled_tools": [
                "get_services",
                "get_staff",
                "get_offers",
                "get_hours",
                "check_availability",
                "book_appointment",
                "cancel_appointment",
                "escalate_to_human",
                "log_unanswered_question",
            ],
        },
        {
            "salon_id": "gentlemans-cut",
            "tone": "Casual, crisp, and direct. Strict rule: maximum two sentences per response. Bilingual in English and Hindi: reply in Hindi when greeted or asked in Hindi, and in English when asked in English.",
            "instructions": (
                "Never use more than two sentences in any response. Closed every Monday without fail. "
                "Walk-ins are welcomed, but bookings take first chair. Classic straight razor shaves include hot towel service."
            ),
            "languages": ["English", "Hindi"],
            "enabled_tools": [
                "get_services",
                "get_staff",
                "get_offers",
                "get_hours",
                "check_availability",
                "book_appointment",
                "cancel_appointment",
                "escalate_to_human",
                "log_unanswered_question",
            ],
        },
    ]

    services_data = [
        # Glow Studio (6 services)
        {"salon_id": "glow-studio", "name": "Signature Haircut & Blowdry", "category": "Hair", "duration_min": 45, "price": 1200},
        {"salon_id": "glow-studio", "name": "Balayage Hair Colour", "category": "Hair", "duration_min": 180, "price": 5500},
        {"salon_id": "glow-studio", "name": "Keratin Smoothing Treatment", "category": "Hair", "duration_min": 120, "price": 4500},
        {"salon_id": "glow-studio", "name": "HydraGlow Deep Cleanse Facial", "category": "Skin", "duration_min": 60, "price": 2200},
        {"salon_id": "glow-studio", "name": "Gel Manicure & Nail Art", "category": "Nails", "duration_min": 60, "price": 1500},
        {"salon_id": "glow-studio", "name": "Pedicure Royale", "category": "Nails", "duration_min": 45, "price": 1100},
        {"salon_id": "glow-studio", "name": "Bridal Makeover & Styling", "category": "Bridal", "duration_min": 150, "price": 12000},

        # Serenity Spa (7 services)
        {"salon_id": "serenity-spa", "name": "Deep Tissue Swedish Massage", "category": "Massages", "duration_min": 60, "price": 3500},
        {"salon_id": "serenity-spa", "name": "Balinese Aromatherapy Ritual", "category": "Massages", "duration_min": 90, "price": 4800},
        {"salon_id": "serenity-spa", "name": "Couples Spa Ritual Package", "category": "Packages", "duration_min": 120, "price": 8500},
        {"salon_id": "serenity-spa", "name": "Radiance Illuminating Facial", "category": "Facials", "duration_min": 60, "price": 3800},
        {"salon_id": "serenity-spa", "name": "Detoxifying Seaweed Body Wrap", "category": "Body Wraps", "duration_min": 75, "price": 4200},
        {"salon_id": "serenity-spa", "name": "Ayurvedic Abhyanga Therapy", "category": "Ayurveda", "duration_min": 60, "price": 3200},
        {"salon_id": "serenity-spa", "name": "Himalayan Pink Salt Scrub", "category": "Body Scrubs", "duration_min": 45, "price": 2600},

        # Gentleman's Cut (6 services)
        {"salon_id": "gentlemans-cut", "name": "Classic Gentleman Haircut", "category": "Hair", "duration_min": 30, "price": 600},
        {"salon_id": "gentlemans-cut", "name": "Royal Hot Towel Shave", "category": "Shave", "duration_min": 30, "price": 450},
        {"salon_id": "gentlemans-cut", "name": "Beard Sculpt & Shape", "category": "Beard", "duration_min": 30, "price": 400},
        {"salon_id": "gentlemans-cut", "name": "Haircut + Beard Styling Combo", "category": "Combos", "duration_min": 45, "price": 900},
        {"salon_id": "gentlemans-cut", "name": "Charcoal Scalp Detox", "category": "Hair Treatment", "duration_min": 30, "price": 750},
        {"salon_id": "gentlemans-cut", "name": "Executive Gray Blending Colour", "category": "Colour", "duration_min": 45, "price": 1100},
    ]

    staff_data = [
        # Glow Studio (3 staff)
        {
            "salon_id": "glow-studio",
            "name": "Ananya Sharma",
            "specialties": ["Signature Haircut & Blowdry", "Balayage Hair Colour", "Bridal Makeover & Styling"],
            "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        },
        {
            "salon_id": "glow-studio",
            "name": "Rohan Verma",
            "specialties": ["Signature Haircut & Blowdry", "Keratin Smoothing Treatment", "Balayage Hair Colour"],
            "working_days": ["tue", "wed", "thu", "fri", "sat", "sun"],
        },
        {
            "salon_id": "glow-studio",
            "name": "Pooja Hegde",
            "specialties": ["HydraGlow Deep Cleanse Facial", "Gel Manicure & Nail Art", "Pedicure Royale"],
            "working_days": ["mon", "wed", "thu", "fri", "sat", "sun"],
        },

        # Serenity Spa (2 staff)
        {
            "salon_id": "serenity-spa",
            "name": "Meera Nair",
            "specialties": ["Deep Tissue Swedish Massage", "Balinese Aromatherapy Ritual", "Couples Spa Ritual Package"],
            "working_days": ["tue", "wed", "thu", "fri", "sat", "sun"],
        },
        {
            "salon_id": "serenity-spa",
            "name": "Devika Rao",
            "specialties": ["Radiance Illuminating Facial", "Detoxifying Seaweed Body Wrap", "Ayurvedic Abhyanga Therapy"],
            "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        },

        # Gentleman's Cut (2 staff)
        {
            "salon_id": "gentlemans-cut",
            "name": "Vikram Singh",
            "specialties": ["Classic Gentleman Haircut", "Royal Hot Towel Shave", "Beard Sculpt & Shape"],
            "working_days": ["tue", "wed", "thu", "fri", "sat", "sun"],
        },
        {
            "salon_id": "gentlemans-cut",
            "name": "Kabir Khan",
            "specialties": ["Haircut + Beard Styling Combo", "Charcoal Scalp Detox", "Executive Gray Blending Colour"],
            "working_days": ["tue", "wed", "thu", "fri", "sat", "sun"],
        },
    ]

    offers_data = [
        # Glow Studio
        {
            "salon_id": "glow-studio",
            "title": "Weekday Glow Deal",
            "description": "Get 20% off all Skin & Nail services Monday through Thursday.",
            "valid_until": "2027-12-31",
        },
        {
            "salon_id": "glow-studio",
            "title": "Bridal Season Perk",
            "description": "Book any Bridal Makeover package and receive a complimentary HydraGlow Facial voucher.",
            "valid_until": "2027-12-31",
        },

        # Serenity Spa
        {
            "salon_id": "serenity-spa",
            "title": "Midweek Serenity Escape",
            "description": "Enjoy a complimentary 15-minute steam and sauna session with any 90-minute massage booked Tue-Thu.",
            "valid_until": "2027-12-31",
        },

        # Gentleman's Cut
        {
            "salon_id": "gentlemans-cut",
            "title": "Father & Son Duo",
            "description": "15% off total bill when father and son book together on weekends.",
            "valid_until": "2027-12-31",
        },
    ]

    # Idempotent upserting
    for salon in salons_data:
        db.salons.replace_one({"_id": salon["_id"]}, salon, upsert=True)

    from app.voice.settings import VoiceSettings
    for cfg in bot_configs_data:
        sid = cfg["salon_id"]
        cfg["voice"] = VoiceSettings(
            voice_id={"glow-studio": "priya", "serenity-spa": "ritu", "gentlemans-cut": "rahul"}[sid],
            pace=0.9 if sid == "serenity-spa" else 1.0,
            greeting={"glow-studio": "Hello, welcome to Glow Studio. How can I help?",
                      "serenity-spa": "Welcome to Serenity. How may we help you today?",
                      "gentlemans-cut": "Hi, welcome to The Gentleman's Cut. What can I do for you?"}[sid]
        ).model_dump()
        db.bot_configs.replace_one({"salon_id": cfg["salon_id"]}, cfg, upsert=True)

    # For services, staff, offers: clear for these salons and re-insert to keep clean
    for salon_id in ["glow-studio", "serenity-spa", "gentlemans-cut"]:
        db.services.delete_many({"salon_id": salon_id})
        db.staff.delete_many({"salon_id": salon_id})
        db.offers.delete_many({"salon_id": salon_id})

    db.services.insert_many(services_data)
    db.staff.insert_many(staff_data)
    db.offers.insert_many(offers_data)

    persist_mock_data()
    print("Database seeded successfully with 3 contrasting salons.")


if __name__ == "__main__":
    seed_database()
