from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Depends
from app.voice.routes import admin_access
from app.db import get_db, serialize_doc, serialize_list, persist_mock_data

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_access)])


@router.get("/conversations")
def get_conversations(salon_id: str = Query(...)):
    """List conversations for a salon with message preview and status."""
    db = get_db()
    convos = list(
        db.conversations.find({"salon_id": salon_id})
        .sort("updated_at", -1)
        .limit(50)
    )
    results = []
    for c in convos:
        msgs = c.get("messages", [])
        last_msg = msgs[-1]["content"] if msgs and "content" in msgs[-1] else ""
        results.append({
            "session_id": c.get("session_id"),
            "status": c.get("status", "active"),
            "message_count": len(msgs),
            "last_message": last_msg[:80] + ("..." if len(last_msg) > 80 else ""),
            "updated_at": c.get("updated_at"),
            "created_at": c.get("created_at"),
        })
    return serialize_list(results)


@router.get("/conversations/{session_id}")
def get_conversation_transcript(session_id: str, salon_id: str = Query(...)):
    """Get full transcript for a specific conversation session including tool calls."""
    db = get_db()
    convo = db.conversations.find_one({"salon_id": salon_id, "session_id": session_id})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation session not found")
    return serialize_doc(convo)


@router.get("/handoffs")
def list_handoffs(salon_id: str = Query(...), status: Optional[str] = None):
    """List customer handoffs/escalations."""
    db = get_db()
    query = {"salon_id": salon_id}
    if status:
        query["status"] = status
    handoffs = list(db.handoffs.find(query).sort("created_at", -1))
    return serialize_list(handoffs)


@router.post("/handoffs/{handoff_id}/resolve")
def resolve_handoff(handoff_id: str, salon_id: str = Query(...)):
    """Mark a human handoff as resolved."""
    db = get_db()
    try:
        oid = ObjectId(handoff_id)
        query = {"_id": oid, "salon_id": salon_id}
    except Exception:
        query = {"_id": handoff_id, "salon_id": salon_id}

    res = db.handoffs.update_one(query, {"$set": {"status": "resolved"}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Handoff not found")
    persist_mock_data()
    return {"success": True, "message": "Handoff marked as resolved"}


@router.get("/unanswered-questions")
def list_unanswered_questions(salon_id: str = Query(...)):
    """List unanswered questions sorted by count descending."""
    db = get_db()
    questions = list(
        db.unanswered_questions.find({"salon_id": salon_id})
        .sort([("count", -1), ("last_asked", -1)])
    )
    return serialize_list(questions)


@router.post("/unanswered-questions/{question_id}/resolve")
def resolve_unanswered_question(question_id: str, salon_id: str = Query(...)):
    """Mark an unanswered question gap as resolved."""
    db = get_db()
    try:
        oid = ObjectId(question_id)
        query = {"_id": oid, "salon_id": salon_id}
    except Exception:
        query = {"_id": question_id, "salon_id": salon_id}

    res = db.unanswered_questions.update_one(query, {"$set": {"resolved": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    persist_mock_data()
    return {"success": True, "message": "Knowledge gap marked as resolved"}


@router.get("/appointments")
def list_appointments(salon_id: str = Query(...)):
    """List confirmed and cancelled appointments for a salon."""
    db = get_db()
    appointments = list(
        db.appointments.find({"salon_id": salon_id})
        .sort("start_time", -1)
    )
    return serialize_list(appointments)
