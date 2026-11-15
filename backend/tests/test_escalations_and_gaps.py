from app.db import get_db
from app.tools import tool_escalate_to_human, tool_log_unanswered_question

def test_escalation_handoff():
    db = get_db()
    session_id = "test_esc_session_99"
    # Create mock active conversation
    db.conversations.update_one(
        {"salon_id": "serenity-spa", "session_id": session_id},
        {"$set": {"status": "active"}},
        upsert=True
    )

    res = tool_escalate_to_human(
        salon_id="serenity-spa",
        reason="Severe allergic skin reaction reported",
        customer_contact="+91 9999000011",
        session_id=session_id,
    )
    assert res["success"] is True
    assert res["status"] == "handed_off"

    # Verify handoff in DB
    handoff = db.handoffs.find_one({"session_id": session_id, "salon_id": "serenity-spa"})
    assert handoff is not None
    assert handoff["status"] == "open"
    assert "allergic" in handoff["reason"].lower()

    # Verify conversation status updated
    convo = db.conversations.find_one({"session_id": session_id, "salon_id": "serenity-spa"})
    assert convo["status"] == "handed_off"


def test_unanswered_question_gap_logging():
    db = get_db()
    q_text = "do you provide home bridal makeup?"

    # Initial log
    res1 = tool_log_unanswered_question("glow-studio", q_text)
    assert res1["logged"] is True

    record1 = db.unanswered_questions.find_one({"salon_id": "glow-studio", "question": q_text})
    assert record1 is not None
    initial_count = record1["count"]

    # Second log should increment count
    res2 = tool_log_unanswered_question("glow-studio", q_text)
    record2 = db.unanswered_questions.find_one({"salon_id": "glow-studio", "question": q_text})
    assert record2["count"] == initial_count + 1
