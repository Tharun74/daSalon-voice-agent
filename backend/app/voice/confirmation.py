"""Server-enforced read-back: approval is tied to an exact booking, not model claims."""
import re
import time
from datetime import datetime
from app.voice.formatter import language_for


def is_yes(text):
    return re.sub(r"[,.!?।]", "", text.strip().lower()) in {
        "okay", "ok", "ஆம்", "ஆமாம்", "சரி", "yes", "yes please", "confirm", "yes confirm", "yes book it", "yes book that", "book it", "go ahead", "haan", "han", "ji haan", "हाँ", "हां", "जी हाँ"
    }


def prepare_booking(arguments, pending, user_text):
    args = {k: str(v).strip() for k, v in arguments.items()
            if k in {"customer_name", "phone", "service_name", "start_time", "staff_name"} and v is not None}
    required = {"customer_name", "phone", "service_name", "start_time"}
    if not required.issubset(args) or not all(args[k] for k in required):
        return False, None, "Please repeat the service, date, time, name and phone number for your booking."
    from app.demo_auth import normalize_phone
    try:
        normalize_phone(args['phone'])
    except ValueError:
        return False, None, "Please enter a valid contact phone number for the booking."
    if (pending and pending.get("args") == args and pending.get("expires", 0) > time.time()
            and pending.get('armed', True) and is_yes(user_text)):
        return True, pending, None
    digits = " ".join(c for c in args["phone"] if c.isdigit())
    try:
        when = datetime.fromisoformat(args["start_time"]).strftime("%d %B %Y at %I:%M %p")
    except ValueError:
        return False, None, "Please repeat the date and time for your booking."
    if language_for(user_text) == "hi-IN":
        reply = f'{args["customer_name"]} के लिए {args["service_name"]}, {when}, फ़ोन {digits}। क्या मैं बुक करूँ?'
    elif language_for(user_text) == "ta-IN":
        reply = f'{args["customer_name"]}, {when}, {args["service_name"]}. புக் செய்யலாமா?'
    else:
        reply = f'Please confirm {args["service_name"]} on {when} for {args["customer_name"]}, phone {digits}. Shall I book it?'
    return False, {"args": args, "expires": time.time() + 300, "armed": True}, reply
