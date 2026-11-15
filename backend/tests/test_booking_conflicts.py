from datetime import datetime, timedelta
from app.tools import tool_book_appointment, tool_cancel_appointment, _get_tz

def test_double_booking_prevention():
    tz = _get_tz()
    # Choose next Wednesday (Ananya works Mon-Sat)
    today = datetime.now(tz).date()
    days_to_wed = (2 - today.weekday()) % 7
    if days_to_wed <= 0:
        days_to_wed += 7
    target_dt = today + timedelta(days=days_to_wed)
    date_str = target_dt.strftime("%Y-%m-%d")
    slot = f"{date_str}T14:00:00"

    # Book with specific staff Ananya
    res1 = tool_book_appointment(
        salon_id="glow-studio",
        customer_name="Customer 1",
        phone="+91 9111111111",
        service_name="Signature Haircut & Blowdry",
        start_time=slot,
        staff_name="Ananya Sharma",
    )
    assert res1["success"] is True

    # Try booking exact same staff at exact same slot -> MUST FAIL
    res2 = tool_book_appointment(
        salon_id="glow-studio",
        customer_name="Customer 2",
        phone="+91 9222222222",
        service_name="Signature Haircut & Blowdry",
        start_time=slot,
        staff_name="Ananya Sharma",
    )
    assert res2["success"] is False
    assert "already booked" in res2["error"].lower()

    # Cancel first booking
    cancel_res = tool_cancel_appointment(
        salon_id="glow-studio",
        phone="+91 9111111111",
        appointment_id=res1["booking_id"],
    )
    assert cancel_res["success"] is True


def test_cancellation_security():
    tz = _get_tz()
    target_dt = datetime.now(tz) + timedelta(days=5)
    date_str = target_dt.strftime("%Y-%m-%d")
    slot = f"{date_str}T15:00:00"

    res = tool_book_appointment(
        salon_id="serenity-spa",
        customer_name="VIP Client",
        phone="+91 9888888888",
        service_name="Deep Tissue Swedish Massage",
        start_time=slot,
    )
    assert res["success"] is True
    booking_id = res["booking_id"]

    # Attempt cancellation with different phone
    unauthorized_cancel = tool_cancel_appointment(
        salon_id="serenity-spa",
        phone="+91 9999999999",
        appointment_id=booking_id,
    )
    assert unauthorized_cancel["success"] is False

    # Attempt cancellation by another salon ID
    cross_tenant_cancel = tool_cancel_appointment(
        salon_id="glow-studio",
        phone="+91 9888888888",
        appointment_id=booking_id,
    )
    assert cross_tenant_cancel["success"] is False

    # Legitimate cancel
    valid_cancel = tool_cancel_appointment(
        salon_id="serenity-spa",
        phone="+91 9888888888",
        appointment_id=booking_id,
    )
    assert valid_cancel["success"] is True
