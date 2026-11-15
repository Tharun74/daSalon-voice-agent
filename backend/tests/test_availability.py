from datetime import datetime, timedelta
from app.tools import tool_check_availability, tool_book_appointment, _get_tz

def test_closed_days():
    # Gentleman's Cut is closed on Mondays
    # Find next Monday
    tz = _get_tz()
    today = datetime.now(tz).date()
    days_ahead = (0 - today.weekday()) % 7  # 0 is Monday
    if days_ahead == 0:
        days_ahead = 7
    next_monday = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    res = tool_check_availability(
        salon_id="gentlemans-cut",
        service_name="Classic Gentleman Haircut",
        date=next_monday,
    )
    assert res["available"] is False
    assert "closed" in res["reason"].lower()


def test_staff_working_days():
    # Ananya Sharma at Glow works mon..sat (not sun)
    tz = _get_tz()
    today = datetime.now(tz).date()
    days_to_sun = (6 - today.weekday()) % 7  # 6 is Sunday
    if days_to_sun == 0:
        days_to_sun = 7
    next_sunday = (today + timedelta(days=days_to_sun)).strftime("%Y-%m-%d")

    res = tool_check_availability(
        salon_id="glow-studio",
        service_name="Signature Haircut & Blowdry",
        date=next_sunday,
        staff_name="Ananya Sharma",
    )
    assert res["available"] is False
    assert "does not work" in res["reason"]


def test_past_slots_rejected():
    tz = _get_tz()
    past_date = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    res = tool_book_appointment(
        salon_id="glow-studio",
        customer_name="John Doe",
        phone="+91 9000000000",
        service_name="Signature Haircut & Blowdry",
        start_time=f"{past_date}T10:00:00",
    )
    assert res["success"] is False
    assert "past" in res["error"].lower()


def test_operating_hours_boundary():
    tz = _get_tz()
    future_date = (datetime.now(tz) + timedelta(days=3)).strftime("%Y-%m-%d")
    # Try booking at 23:00 (outside hours)
    res = tool_book_appointment(
        salon_id="glow-studio",
        customer_name="Late Night",
        phone="+91 9000000000",
        service_name="Signature Haircut & Blowdry",
        start_time=f"{future_date}T23:00:00",
    )
    assert res["success"] is False
    assert "operating hours" in res["error"].lower()
