import uuid
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import threading
import time

from app.db import get_db, persist_mock_data
from app.prompts import build_system_prompt
from app.llm import complete, clean_content
from app.tools import TOOL_SCHEMAS, execute_tool_call
from app.rag import retrieve_reference_context

logger = logging.getLogger("dasalon.chat")

def get_or_create_conversation(salon_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve existing conversation or initialize a new session."""
    db = get_db()
    if not session_id:
        session_id = str(uuid.uuid4())

    conv = db.conversations.find_one({"salon_id": salon_id, "session_id": session_id})
    if not conv:
        conv = {
            "salon_id": salon_id,
            "session_id": session_id,
            "channel": "web",
            "messages": [],
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        db.conversations.insert_one(conv)
        persist_mock_data()
    return conv


def _turn_events_unlocked(
    salon_id: str,
    session_id: Optional[str],
    user_message: str,
    execute_tools: bool = True,
    reference_docs: Optional[str] = None,
    channel: str = "text",
    stream: bool = False,
    cancel=None,
    turn_id=None,
    uncertain=False,
) -> Dict[str, Any]:
    """
    Main chat orchestration function:
    1. Loads salon profile & bot configuration
    2. Retrieves conversation history
    3. Assembles prompt
    4. Calls LLM with tool definitions
    5. Executes tool calls in a loop (up to 5 iterations)
    6. Persists conversation including tool calls to database
    7. Returns clean reply and session_id
    """
    if channel not in {"text", "voice"}:
        raise ValueError("Invalid channel")
    db = get_db()
    salon = db.salons.find_one({"_id": salon_id})
    if not salon:
        raise ValueError(f"Salon '{salon_id}' not found")

    bot_config = db.bot_configs.find_one({"salon_id": salon_id}) or {}

    conv = get_or_create_conversation(salon_id, session_id)
    session_id = conv["session_id"]
    pending_booking = conv.get("voice_pending_booking")
    # A yes after an unrelated question must not approve an older read-back.
    from app.voice.confirmation import is_yes
    if pending_booking and not is_yes(user_message):
        pending_booking = {**pending_booking, 'armed': False}
    booking_readback = None
    is_handed_off = conv.get("status") == "handed_off"

    # If conversation is already handed off, gently remind customer
    if is_handed_off:
        result = {
            "reply": (
                "This demo cannot transfer you or arrange a callback. Please contact the salon at "
                f"{salon.get('phone', 'our reception')}."
            ),
            "session_id": session_id,
            "status": "handed_off",
        }
        if channel == "voice":
            events = [{"role": role, "content": content, "channel": "voice", "turn_id": turn_id,
                       "created_at": datetime.utcnow().isoformat()}
                      for role, content in [("user", user_message), ("assistant", result["reply"])]]
            db.conversations.update_one({"salon_id": salon_id, "session_id": session_id},
                {"$push": {"messages": {"$each": events}}, "$set": {"updated_at": datetime.utcnow()}})
            persist_mock_data()
        yield {"type": "result", "result": result}
        return

    now_iso = datetime.utcnow().isoformat()
    new_convo_events = []

    persisted = False
    try:
        # 1. Record user message
        user_msg_entry = {
            "role": "user",
            "content": user_message,
            "created_at": now_iso,
        }
        new_convo_events.append(user_msg_entry)
        from app.conversation_policy import direct_reply
        control_reply, control = direct_reply(user_message, salon)
        if control:
            pending_booking = None
            db.conversations.update_one({'salon_id': salon_id, 'session_id': session_id},
                {'$unset': {'booking_consent': ''}, '$set': {'phone_required': False}})

        # 2. Build history from past 20 messages for LLM context
        past_messages = conv.get("messages", [])[-(8 if channel == "voice" else 20):]
        llm_messages = []
        for m in past_messages:
            role = m.get("role", "user")
            if role in ["user", "assistant"]:
                llm_messages.append({"role": role, "content": m.get("content", "")})

        # 2.5 Retrieve verified reference documents via RAG (strictly filtered by salon_id)
        if reference_docs is None and channel != "voice":
            try:
                reference_docs = retrieve_reference_context(salon_id=salon_id, query=user_message)
            except Exception as e:
                logger.warning(f"Error retrieving RAG context: {e}")
                reference_docs = None

        # 3. Assemble system prompt
        system_prompt = build_system_prompt(salon, bot_config, reference_docs=reference_docs)
        system_prompt += ('\nBOOKING FLOW: Use tools for current prices, offers and slots. '
            'Before booking, read back the service, stylist, date/time and price and ask for confirmation. '
            'If a tool returns phone_required, ask the customer to complete the phone form in this panel. '
            'This is a demo: any six-digit code is accepted and no SMS is sent. Never claim actual phone ownership verification. '
            'Only report a successful demo booking when book_appointment returns success=true. '
            'A saved demo booking is not a real salon appointment. '
            'For treatment aftercare, search salon knowledge and answer only from approved content. '
            'If guidance is missing, say so and suggest consulting the salon. '
            'Do not claim a human was contacted unless a real handoff has occurred.')
        if conv.get('demo_phone'):
            system_prompt += '\nServer-confirmed demo phone step completed for: ' + conv['demo_phone']
        if conv.get('last_booking'):
            system_prompt += '\nLatest successful demo booking: ' + json.dumps(conv['last_booking'], default=str)
        if pending_booking:
            system_prompt += '\nUnfinished booking draft (not a confirmed appointment): ' + json.dumps(pending_booking['args'])
            system_prompt += '\nRetain these details across questions. Changes require a new check and confirmation.'
        if channel == "voice":
            from app.voice.settings import VOICE_ADDENDUM
            system_prompt += "\n" + VOICE_ADDENDUM
        active_messages = [{"role": "system", "content": system_prompt}] + llm_messages + [{"role": "user", "content": user_message}]

        # 4. Filter enabled tools from bot_config if specified
        enabled_tool_names = bot_config.get("enabled_tools")
        active_tools = TOOL_SCHEMAS
        if enabled_tool_names is not None:
            active_tools = [t for t in TOOL_SCHEMAS if t["function"]["name"] in enabled_tool_names]
        active_tools = [t for t in active_tools if t['function']['name'] not in {'cancel_appointment', 'escalate_to_human'}]

        if channel == "voice":
            active_tools = list(active_tools) + [{"type": "function", "function": {
                "name": "search_salon_knowledge", "description": "Look up salon policies or reference details only when needed to answer the caller.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}]

        tools_param = active_tools if execute_tools and active_tools else None

        # 5. Tool execution loop (max 5 turns)
        max_tool_iterations = 5
        iteration = 0
        final_reply = control_reply or ""
        unresolved = conv.get('unresolved_booking')
        if unresolved:
            from app.partner_api import call_partner
            recovered = call_partner('get_booking_status', unresolved, salon_id, session_id)
            if recovered.get('success'):
                pending_booking = None
                db.conversations.update_one({'salon_id': salon_id, 'session_id': session_id},
                    {'$unset': {'unresolved_booking': ''}, '$set': {'last_booking': recovered}})
                final_reply = f"Your original demo booking is confirmed: {recovered['service']} with {recovered['staff']}, {recovered['start_time']}. Reference {recovered['booking_id']}."
            else:
                final_reply = "The previous booking result is still unknown. I won't create another appointment until it is resolved. Please contact the salon if you need help."

        while iteration < max_tool_iterations:
            if final_reply:
                break
            if uncertain:
                final_reply = "I could not hear that clearly. Could you please repeat?"
                break
            iteration += 1
            try:
                if cancel and cancel.is_set():
                    return
                if stream:
                    from app.llm import complete_stream
                    for event in complete_stream(active_messages, tools_param):
                        if cancel and cancel.is_set():
                            return
                        if event["type"] == "message":
                            msg = event["message"]
                        else:
                            yield event
                else:
                    msg = complete(messages=active_messages, tools=tools_param, temperature=0.2,
                                   max_tokens=120 if channel == "voice" else 1000)
            except Exception as e:
                logger.error(f"Error from LLM in tool loop turn {iteration}: {e}")
                final_reply = "I apologize, but I encountered a momentary connection issue. Please feel free to ask again or call our salon."
                break

            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls:
                # Final text response
                final_reply = clean_content(msg.content or "")
                break

            # If model returned tool calls, process them
            logger.info(f"LLM produced {len(tool_calls)} tool calls in turn {iteration}")

            # Add assistant message with tool calls to prompt history
            assistant_turn_for_llm = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            active_messages.append(assistant_turn_for_llm)

            # Log to conversation history for admin transcript
            new_convo_events.append({
                "role": "assistant_tool_call",
                "content": msg.content or "",
                "tool_calls": [
                    {"name": tc.function.name, "arguments": tc.function.arguments, "id": tc.id}
                    for tc in tool_calls
                ],
                "created_at": datetime.utcnow().isoformat(),
            })

            # Execute each tool call
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                except Exception:
                    fn_args = {}

                logger.info(f"Executing tool {fn_name} for salon_id={salon_id}")
                if cancel and cancel.is_set():
                    return
                yield {"type": "tool_event", "phase": "start", "name": fn_name}
                if cancel and cancel.is_set():
                    return
                if not isinstance(fn_args, dict):
                    fn_args = {}
                # CRITICAL: salon_id is injected from session context!
                booking_allowed = True
                if fn_name == "book_appointment":
                    from app.voice.confirmation import prepare_booking
                    from app.tools import _find_service
                    service = _find_service(salon_id, str(fn_args.get('service_name', '')))
                    quote = {'price': service.get('price'), 'duration_min': service.get('duration_min')} if service else None
                    if pending_booking and pending_booking.get('quote') != quote:
                        pending_booking = {**pending_booking, 'armed': False}
                    booking_allowed, pending_booking, booking_readback = prepare_booking(
                        fn_args, pending_booking, user_message)
                    if booking_readback and pending_booking:
                        pending_booking['quote'] = quote
                        staff = fn_args.get('staff_name') or 'an available stylist'
                        if service:
                            from app.tools import _get_tz
                            when = datetime.fromisoformat(fn_args['start_time'])
                            if when.tzinfo:
                                when = when.astimezone(_get_tz())
                            booking_readback = (f"Please confirm {service['name']} with {staff}, "
                                f"on {when.strftime('%A, %d %B at %I:%M %p')}, for {fn_args.get('customer_name', '')}. "
                                f"It takes {service.get('duration_min', 30)} minutes and costs {service['price']} rupees. Shall I book this demo appointment?")
                allowed_names = {tool["function"]["name"] for tool in active_tools}
                if not execute_tools or fn_name not in allowed_names:
                    tool_result = {"error": "This action is not enabled."}
                elif fn_name == "search_salon_knowledge":
                    tool_result = {"reference": retrieve_reference_context(salon_id=salon_id, query=str(fn_args.get("query", ""))[:500])}
                elif not booking_allowed:
                    tool_result = {"confirmation_required": True, "readback": booking_readback}
                else:
                    if fn_name == 'book_appointment':
                        from app.partner_api import booking_fingerprint
                        db.conversations.update_one({'salon_id': salon_id, 'session_id': session_id},
                            {'$set': {'booking_consent': {'fingerprint': booking_fingerprint(fn_args),
                             'expires': time.time() + 300, 'quote': quote}}})
                    tool_result = execute_tool_call(
                        tool_name=fn_name,
                        arguments=fn_args,
                        salon_id=salon_id,
                        session_id=session_id,
                    )

                if fn_name == 'book_appointment' and tool_result.get('success'):
                    pending_booking = None
                    final_reply = (f"Your demo appointment is booked: {tool_result['service']} with {tool_result['staff']}, "
                        f"{tool_result['start_time']}, {tool_result['price']}. Reference {tool_result['booking_id']}. "
                        "This is a demo booking, not a real salon appointment.")
                elif fn_name == 'book_appointment' and tool_result.get('status') == 'unknown':
                    db.conversations.update_one({'salon_id': salon_id, 'session_id': session_id},
                        {'$set': {'unresolved_booking': fn_args}})
                    final_reply = "I haven't received a confirmed booking result. I'll check the original request before attempting another appointment."
                elif fn_name == 'book_appointment' and tool_result.get('phone_required'):
                    final_reply = "Please complete the phone form below. This demo accepts any six-digit code and sends no SMS. Then I'll read back your appointment for confirmation."
                result_str = json.dumps(tool_result, default=str)
                active_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

                new_convo_events.append({
                    "role": "tool_result",
                    "tool_name": fn_name,
                    "tool_call_id": tc.id,
                    "result": tool_result,
                    "created_at": datetime.utcnow().isoformat(),
                })
                yield {"type": "tool_event", "phase": "end", "name": fn_name}
                if final_reply:
                    break
                if booking_readback:
                    break  # Never let another tool call approve a read-back in this turn.

            if booking_readback:
                final_reply = booking_readback
                break

        if not final_reply and iteration >= max_tool_iterations:
            final_reply = "I couldn't finish checking those details. No new booking is confirmed. Please try again or contact the salon."

        if cancel and cancel.is_set():
            return
        if channel == "voice" and not booking_readback:
            from app.llm import SpeechBudget
            final_reply = SpeechBudget().feed(final_reply).strip()
        # Persist assistant final response
        assistant_final_entry = {
            "role": "assistant",
            "content": final_reply,
            "created_at": datetime.utcnow().isoformat(),
        }
        new_convo_events.append(assistant_final_entry)

        # Check if any tool changed status to handed_off
        conv_now = db.conversations.find_one({"salon_id": salon_id, "session_id": session_id})
        current_status = conv_now.get("status", "active") if conv_now else "active"

        for event in new_convo_events:
            event["channel"] = channel
            if turn_id:
                event["turn_id"] = turn_id

        db.conversations.update_one(
            {"salon_id": salon_id, "session_id": session_id},
            {
                "$push": {"messages": {"$each": new_convo_events}},
                "$set": {"updated_at": datetime.utcnow(), "voice_pending_booking": pending_booking},
            },
        )
        persist_mock_data()

        persisted = True
        yield {"type": "result", "result": {
            "reply": final_reply,
            "session_id": session_id,
            "status": current_status,
        }}
    finally:
        if channel == "voice" and not persisted and cancel and cancel.is_set() and new_convo_events:
            for event in new_convo_events:
                event.update(channel="voice", turn_id=turn_id, interrupted=True)
            db.conversations.update_one(
                {"salon_id": salon_id, "session_id": session_id},
                {"$push": {"messages": {"$each": new_convo_events}},
                 "$set": {"updated_at": datetime.utcnow()}})
            persist_mock_data()


def run_turn(salon_id, session_id, user_text, channel="text", **kwargs):
    """Shared channel-independent brain; preserve the original result contract."""
    for event in _turn_events(salon_id, session_id, user_text, channel=channel, **kwargs):
        if event["type"] == "result":
            return event["result"]
    raise RuntimeError("Turn interrupted")


def run_turn_stream(salon_id, session_id, user_text, channel="voice", cancel=None, turn_id=None):
    yield from _turn_events(salon_id, session_id, user_text, channel=channel,
                            stream=True, cancel=cancel, turn_id=turn_id)


def orchestrate_chat(salon_id, session_id, user_message, execute_tools=True, reference_docs=None):
    """Compatibility entry point for existing callers and /chat."""
    return run_turn(salon_id, session_id, user_message, execute_tools=execute_tools,
                    reference_docs=reference_docs)


# Bounded striped locks serialize shared text/voice histories in the demo process.
_turn_locks = [threading.Lock() for _ in range(128)]


def _turn_events(salon_id, session_id, *args, **kwargs):
    lock = _turn_locks[hash((salon_id, session_id)) % len(_turn_locks)]
    with lock:
        yield from _turn_events_unlocked(salon_id, session_id, *args, **kwargs)
