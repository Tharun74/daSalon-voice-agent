import re
import threading
from functools import wraps
import json
from datetime import datetime, date, time, timedelta
from typing import Dict, Any, List, Optional
from bson import ObjectId
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

from app import config
from app.db import get_db, persist_mock_data, serialize_doc, serialize_list

# Tool schemas in OpenAI format
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_services",
            "description": "List all services, prices (INR), and durations for this salon. Optionally filter by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Optional category to filter services (e.g. Hair, Skin, Nails, Massages, Bridal)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_staff",
            "description": "List staff members, their specialties, and their working days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Optional service name to find specialists for that service",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_offers",
            "description": "List current active promotional offers and discounts.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hours",
            "description": "Get weekly operating hours and check if the salon is currently open.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check available appointment time slots on a specific date for a service and optional preferred staff member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "The exact or partial name of the service (e.g. 'Signature Haircut', 'Swedish Massage')",
                    },
                    "date": {
                        "type": "string",
                        "description": "The date in YYYY-MM-DD format (e.g. '2026-11-05')",
                    },
                    "staff_name": {
                        "type": "string",
                        "description": "Optional name of preferred staff member",
                    },
                },
                "required": ["service_name", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a confirmed appointment. Re-validates slot availability server-side before booking. Requires customer name, phone, service, and start time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Full name of the customer",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Customer phone number (e.g. '+91 9876543210')",
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service to book",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in ISO format YYYY-MM-DDTHH:MM or 'YYYY-MM-DD HH:MM'",
                    },
                    "staff_name": {
                        "type": "string",
                        "description": "Optional preferred staff member name",
                    },
                },
                "required": ["customer_name", "phone", "service_name", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment. Validates that the phone number matches the booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Customer's phone number registered on the booking",
                    },
                    "appointment_id": {
                        "type": "string",
                        "description": "The appointment ID to cancel",
                    },
                },
                "required": ["phone", "appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escalate the conversation to human staff or manager when customer has a complaint, allergy, medical question, dispute, or complex request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for escalation (e.g. 'Customer complaint', 'Allergy concern', 'Custom bridal quote')",
                    },
                    "customer_contact": {
                        "type": "string",
                        "description": "Customer's phone number or email if provided",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_unanswered_question",
            "description": "Log questions that the bot cannot answer or where salon information is missing, so owners can update knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The exact user question that could not be answered",
                    }
                },
                "required": ["question"],
            },
        },
    },
]


def _get_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(config.TIMEZONE)
    except Exception:
        import pytz
        return pytz.timezone(config.TIMEZONE)


# --- Tool Implementations (salon_id ALWAYS server-injected) ---

def tool_get_services(salon_id: str, category: Optional[str] = None) -> Dict[str, Any]:
    db = get_db()
    query: Dict[str, Any] = {"salon_id": salon_id}
    if category:
        query["category"] = {"$regex": f"^{re.escape(category.strip())}", "$options": "i"}

    services = list(db.services.find(query))
    if not services and category:
        # Fallback to all services if category filter yields none
        services = list(db.services.find({"salon_id": salon_id}))

    return {
        "services": [
            {
                "id": str(s["_id"]),
                "name": s["name"],
                "category": s["category"],
                "duration_min": s["duration_min"],
                "price": f"INR {s['price']}",
            }
            for s in services
        ]
    }


def tool_get_staff(salon_id: str, service_name: Optional[str] = None) -> Dict[str, Any]:
    db = get_db()
    staff_members = list(db.staff.find({"salon_id": salon_id}))
    result = []
    for member in staff_members:
        specializes = True
        if service_name:
            specializes = any(
                service_name.lower() in spec.lower() or spec.lower() in service_name.lower()
                for spec in member.get("specialties", [])
            )
        result.append(
            {
                "id": str(member["_id"]),
                "name": member["name"],
                "specialties": member.get("specialties", []),
                "working_days": member.get("working_days", []),
                "specializes_in_requested": specializes,
            }
        )
    return {"staff": result}


def tool_get_offers(salon_id: str) -> Dict[str, Any]:
    db = get_db()
    today_str = datetime.now(_get_tz()).strftime("%Y-%m-%d")
    offers = list(db.offers.find({
        "salon_id": salon_id,
        "valid_until": {"$gte": today_str},
    }))
    return {
        "offers": [
            {
                "title": o["title"],
                "description": o["description"],
                "valid_until": o["valid_until"],
            }
            for o in offers
        ]
    }


def tool_get_hours(salon_id: str) -> Dict[str, Any]:
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        return {"error": "Salon not found"}

    hours = salon.get("hours", {})
    now = datetime.now(_get_tz())
    current_day = now.strftime("%a").lower()[:3]
    today_hours = hours.get(current_day, "closed")

    is_open = False
    if today_hours.lower() != "closed" and "-" in today_hours:
        try:
            start_str, end_str = today_hours.split("-")
            sh, sm = map(int, start_str.strip().split(":"))
            eh, em = map(int, end_str.strip().split(":"))
            open_time = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            close_time = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            is_open = open_time <= now <= close_time
        except Exception:
            is_open = False

    return {
        "weekly_hours": hours,
        "current_day": current_day,
        "today_hours": today_hours,
        "is_currently_open": is_open,
        "current_time": now.strftime("%Y-%m-%d %I:%M %p %Z"),
    }


def _find_service(salon_id: str, service_name: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    # Exact match first
    srv = db.services.find_one({
        "salon_id": salon_id,
        "name": {"$regex": f"^{re.escape(service_name.strip())}$", "$options": "i"},
    })
    if not srv:
        # Partial match
        srv = db.services.find_one({
            "salon_id": salon_id,
            "name": {"$regex": re.escape(service_name.strip()), "$options": "i"},
        })
    return srv


def tool_check_availability(
    salon_id: str,
    service_name: str,
    date: str,
    staff_name: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        return {"error": "Salon not found"}

    service = _find_service(salon_id, service_name)
    if not service:
        all_services = [s["name"] for s in db.services.find({"salon_id": salon_id})]
        return {
            "available": False,
            "error": f"Service '{service_name}' not found. Available services: {', '.join(all_services)}",
        }

    try:
        # Normalize date
        target_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return {"available": False, "error": "Invalid date format. Please use YYYY-MM-DD."}

    day_of_week = target_date.strftime("%a").lower()[:3]
    hours = salon.get("hours", {})
    day_hours = hours.get(day_of_week, "closed")

    if day_hours.lower() == "closed" or "-" not in day_hours:
        return {
            "available": False,
            "date": str(target_date),
            "reason": f"Salon is closed on {target_date.strftime('%A')} ({day_of_week.capitalize()}).",
        }

    start_str, end_str = day_hours.split("-")
    open_h, open_m = map(int, start_str.strip().split(":"))
    close_h, close_m = map(int, end_str.strip().split(":"))

    open_dt = datetime.combine(target_date, time(open_h, open_m))
    close_dt = datetime.combine(target_date, time(close_h, close_m))

    # Eligible staff
    staff_query: Dict[str, Any] = {"salon_id": salon_id, "working_days": day_of_week}
    if staff_name:
        staff_query["name"] = {"$regex": re.escape(staff_name.strip()), "$options": "i"}

    all_staff_day = list(db.staff.find(staff_query))
    # Match service specialty
    srv_lower = service["name"].lower()
    specialized_staff = [
        s for s in all_staff_day
        if any(srv_lower in spec.lower() or spec.lower() in srv_lower for spec in s.get("specialties", []))
    ]
    eligible_staff = specialized_staff
    if not eligible_staff:
        if staff_name:
            return {
                "available": False,
                "reason": (f"{staff_name} does not work on {target_date.strftime('%A')}." if not all_staff_day else f"{staff_name} is not eligible for this service."),
            }
        return {
            "available": False,
            "reason": f"No staff members on duty on {target_date.strftime('%A')}.",
        }

    # Fetch existing appointments on that date
    date_str_prefix = target_date.strftime("%Y-%m-%d")
    existing_appts = list(
        db.appointments.find({
            "salon_id": salon_id,
            "status": "confirmed",
            "start_time": {"$regex": f"^{date_str_prefix}"},
        })
    )

    tz = _get_tz()
    now_in_tz = datetime.now(tz).replace(tzinfo=None)  # naive comparison

    duration_min = service.get("duration_min", 30)
    slot_interval = 30  # grid in minutes
    available_slots = []

    current_slot = open_dt
    while current_slot + timedelta(minutes=duration_min) <= close_dt:
        slot_end = current_slot + timedelta(minutes=duration_min)

        # Check if slot is in the past
        if current_slot <= now_in_tz:
            current_slot += timedelta(minutes=slot_interval)
            continue

        # Check if any eligible staff is free for this window
        free_staff_for_slot = []
        for member in eligible_staff:
            member_id = str(member["_id"])
            member_name = member["name"]

            # Check overlap with existing appointments for this staff
            is_booked = False
            for appt in existing_appts:
                # Compare staff
                if appt.get("staff_id") == member_id or appt.get("staff_name") == member_name:
                    try:
                        # parse appt start & end
                        a_start = datetime.fromisoformat(appt["start_time"].replace("Z", ""))
                        a_end = datetime.fromisoformat(appt["end_time"].replace("Z", ""))
                        # Check overlap: (slot_start < a_end) and (slot_end > a_start)
                        if current_slot < a_end and slot_end > a_start:
                            is_booked = True
                            break
                    except Exception:
                        pass
            if not is_booked:
                free_staff_for_slot.append(member_name)

        if free_staff_for_slot:
            available_slots.append({
                "time": current_slot.strftime("%H:%M"),
                "start_time_iso": current_slot.isoformat(),
                "available_staff": free_staff_for_slot,
            })

        current_slot += timedelta(minutes=slot_interval)

    return {
        "available": len(available_slots) > 0,
        "date": str(target_date),
        "service": service["name"],
        "duration_min": duration_min,
        "available_slots": [s["time"] for s in available_slots],
        "slot_details": available_slots,
    }


# Serialize overlap check + insertion in this single-process demo.
_booking_lock = threading.RLock()


def _atomic_demo_booking(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _booking_lock:
            return fn(*args, **kwargs)
    return wrapped


@_atomic_demo_booking
def tool_book_appointment(
    salon_id: str,
    customer_name: str,
    phone: str,
    service_name: str,
    start_time: str,
    staff_name: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        return {"success": False, "error": "Salon not found"}

    service = _find_service(salon_id, service_name)
    if not service:
        return {"success": False, "error": f"Service '{service_name}' not found."}

    # Normalize start_time
    clean_time_str = start_time.strip().replace(" ", "T")
    try:
        start_dt = datetime.fromisoformat(clean_time_str)
        if start_dt.tzinfo is not None:
            start_dt = start_dt.astimezone(_get_tz()).replace(tzinfo=None)
    except ValueError:
        return {"success": False, "error": "Invalid start_time format. Use YYYY-MM-DDTHH:MM."}

    duration_min = service.get("duration_min", 30)
    end_dt = start_dt + timedelta(minutes=duration_min)

    # Check future
    tz = _get_tz()
    now_in_tz = datetime.now(tz).replace(tzinfo=None)
    if start_dt <= now_in_tz:
        return {"success": False, "error": "Cannot book appointment in the past."}

    # Check operating hours
    day_of_week = start_dt.strftime("%a").lower()[:3]
    hours = salon.get("hours", {})
    day_hours = hours.get(day_of_week, "closed")
    if day_hours.lower() == "closed" or "-" not in day_hours:
        return {"success": False, "error": f"Salon is closed on {start_dt.strftime('%A')}."}

    open_h, open_m = map(int, day_hours.split("-")[0].strip().split(":"))
    close_h, close_m = map(int, day_hours.split("-")[1].strip().split(":"))
    open_dt = datetime.combine(start_dt.date(), time(open_h, open_m))
    close_dt = datetime.combine(start_dt.date(), time(close_h, close_m))

    if start_dt < open_dt or end_dt > close_dt:
        return {
            "success": False,
            "error": f"Appointment outside salon operating hours ({open_h:02d}:{open_m:02d} to {close_h:02d}:{close_m:02d}).",
        }

    # Staff selection & double-booking prevention
    staff_query: Dict[str, Any] = {"salon_id": salon_id, "working_days": day_of_week}
    if staff_name:
        staff_query["name"] = {"$regex": re.escape(staff_name.strip()), "$options": "i"}

    all_staff_day = list(db.staff.find(staff_query))
    srv_lower = service["name"].lower()
    specialized_staff = [
        s for s in all_staff_day
        if any(srv_lower in spec.lower() or spec.lower() in srv_lower for spec in s.get("specialties", []))
    ]
    candidate_staff = specialized_staff
    if not candidate_staff:
        return {
            "success": False,
            "error": f"No staff available on {start_dt.strftime('%A')}" + (f" named {staff_name}" if staff_name else ""),
        }

    # Check existing appointments for overlap
    date_str_prefix = start_dt.strftime("%Y-%m-%d")
    existing_appts = list(
        db.appointments.find({
            "salon_id": salon_id,
            "status": "confirmed",
            "start_time": {"$regex": f"^{date_str_prefix}"},
        })
    )

    chosen_staff = None
    for member in candidate_staff:
        member_id = str(member["_id"])
        member_name = member["name"]
        conflict = False
        for appt in existing_appts:
            if appt.get("staff_id") == member_id or appt.get("staff_name") == member_name:
                try:
                    a_start = datetime.fromisoformat(appt["start_time"].replace("Z", ""))
                    a_end = datetime.fromisoformat(appt["end_time"].replace("Z", ""))
                    if start_dt < a_end and end_dt > a_start:
                        conflict = True
                        break
                except Exception:
                    pass
        if not conflict:
            chosen_staff = member
            break

    if not chosen_staff:
        # Check alternative slots for the day
        avail = tool_check_availability(
            salon_id=salon_id,
            service_name=service["name"],
            date=start_dt.strftime("%Y-%m-%d"),
            staff_name=staff_name,
        )
        return {
            "success": False,
            "error": f"Slot at {start_dt.strftime('%I:%M %p')} is already booked.",
            "alternative_slots": avail.get("available_slots", [])[:5],
        }

    # Insert confirmed appointment
    appt_record = {
        "salon_id": salon_id,
        "customer_name": customer_name.strip(),
        "phone": phone.strip(),
        "service_id": str(service["_id"]),
        "service_name": service["name"],
        "staff_id": str(chosen_staff["_id"]),
        "staff_name": chosen_staff["name"],
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "price": service["price"],
        "status": "confirmed",
        "created_at": datetime.utcnow(),
    }
    insert_res = db.appointments.insert_one(appt_record)
    persist_mock_data()

    booking_id = str(insert_res.inserted_id)
    return {
        "success": True,
        "booking_id": booking_id,
        "salon_name": salon.get("name"),
        "customer_name": customer_name,
        "phone": phone,
        "service": service["name"],
        "staff": chosen_staff["name"],
        "start_time": start_dt.strftime("%A, %B %d, %Y at %I:%M %p"),
        "end_time": end_dt.strftime("%I:%M %p"),
        "price": f"INR {service['price']}",
        "status": "confirmed",
        "message": f"Appointment booked successfully for {customer_name}! Booking ID: {booking_id}",
    }


def tool_cancel_appointment(
    salon_id: str,
    phone: str,
    appointment_id: str,
) -> Dict[str, Any]:
    db = get_db()
    # Support both string _id and ObjectId
    match_query: Dict[str, Any] = {"salon_id": salon_id, "phone": phone.strip()}
    try:
        match_query["_id"] = ObjectId(appointment_id.strip())
    except Exception:
        match_query["_id"] = appointment_id.strip()

    appt = db.appointments.find_one(match_query)
    if not appt:
        # Also try matching as string if ObjectId failed or vice versa
        appt = db.appointments.find_one({"salon_id": salon_id, "phone": phone.strip()})
        if not appt or str(appt.get("_id")) != appointment_id.strip():
            return {
                "success": False,
                "error": "No appointment found matching this ID and phone number for this salon.",
            }

    if appt.get("status") == "cancelled":
        return {"success": False, "message": "This appointment has already been cancelled."}

    db.appointments.update_one(
        {"_id": appt["_id"], "salon_id": salon_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.utcnow()}},
    )
    persist_mock_data()

    return {
        "success": True,
        "appointment_id": str(appt["_id"]),
        "service": appt.get("service_name"),
        "start_time": appt.get("start_time"),
        "message": f"Appointment {str(appt['_id'])} has been successfully cancelled.",
    }


def tool_escalate_to_human(
    salon_id: str,
    reason: str,
    customer_contact: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_db()
    handoff_record = {
        "salon_id": salon_id,
        "session_id": session_id or "unknown",
        "reason": reason,
        "customer_contact": customer_contact or "Not provided",
        "status": "open",
        "created_at": datetime.utcnow(),
    }
    res = db.handoffs.insert_one(handoff_record)

    if session_id:
        db.conversations.update_one(
            {"salon_id": salon_id, "session_id": session_id},
            {"$set": {"status": "handed_off", "updated_at": datetime.utcnow()}},
        )

    persist_mock_data()
    return {
        "success": True,
        "handoff_id": str(res.inserted_id),
        "status": "handed_off",
        "message": "The conversation has been forwarded to human salon staff. A team member will follow up shortly.",
    }


def tool_log_unanswered_question(salon_id: str, question: str) -> Dict[str, Any]:
    db = get_db()
    clean_q = question.strip().lower()
    db.unanswered_questions.update_one(
        {"salon_id": salon_id, "question": clean_q},
        {
            "$inc": {"count": 1},
            "$set": {"last_asked": datetime.utcnow(), "resolved": False},
        },
        upsert=True,
    )
    persist_mock_data()
    return {
        "logged": True,
        "question": clean_q,
    }


# Router map for tool calls
TOOL_DISPATCH = {
    "get_services": tool_get_services,
    "get_staff": tool_get_staff,
    "get_offers": tool_get_offers,
    "get_hours": tool_get_hours,
    "check_availability": tool_check_availability,
    "book_appointment": tool_book_appointment,
    "cancel_appointment": tool_cancel_appointment,
    "escalate_to_human": tool_escalate_to_human,
    "log_unanswered_question": tool_log_unanswered_question,
}


def execute_tool_call(tool_name: str, arguments: Dict[str, Any], salon_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    CRITICAL SECURITY & MULTI-TENANCY REQUIREMENT:
    salon_id is injected SERVER-SIDE and NEVER accepted from LLM arguments.
    """
    if tool_name in {'cancel_appointment', 'escalate_to_human'}:
        return {'success': False, 'unsupported': True,
                'message': 'This demo cannot change existing appointments or contact staff. Offer the public salon contact; no transfer or callback has occurred.'}
    if tool_name not in TOOL_DISPATCH:
        return {"error": f"Unknown tool: {tool_name}"}

    func = TOOL_DISPATCH[tool_name]
    # Remove any rogue salon_id if the model tried to supply one
    arguments = {key: value for key, value in arguments.items() if key != 'salon_id'}

    try:
        if tool_name in {"get_services", "get_staff", "get_offers", "get_hours", "check_availability", "book_appointment"}:
            from app.partner_api import call_partner
            return call_partner(tool_name, arguments, salon_id, session_id)
        if tool_name == "escalate_to_human":
            return func(salon_id=salon_id, session_id=session_id, **arguments)
        else:
            return func(salon_id=salon_id, **arguments)
    except Exception as e:
        return {"error": f"Failed executing {tool_name}: {str(e)}"}
