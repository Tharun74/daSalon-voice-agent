import time
from collections import defaultdict
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.chat import orchestrate_chat

router = APIRouter(tags=["chat"])

# In-memory sliding window rate limiter per session
_session_request_times = defaultdict(list)
RATE_LIMIT_PER_MINUTE = 30


def is_rate_limited(session_key: str, max_requests: int = RATE_LIMIT_PER_MINUTE, window_sec: int = 60) -> bool:
    now = time.time()
    recent = [t for t in _session_request_times[session_key] if now - t < window_sec]
    if len(recent) >= max_requests:
        return True
    recent.append(now)
    _session_request_times[session_key] = recent
    return False


class ChatRequest(BaseModel):
    salon_id: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = Field(None, max_length=150)
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    status: Optional[str] = "active"


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    """Core multi-tenant chat endpoint with rate-limiting and validation."""
    rate_key = payload.session_id or f"{payload.salon_id}_anon"
    if is_rate_limited(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You're sending messages a bit too fast. Please wait a few seconds before trying again.",
        )

    try:
        result = orchestrate_chat(
            salon_id=payload.salon_id,
            session_id=payload.session_id,
            user_message=payload.message,
            execute_tools=True,
        )
        return ChatResponse(
            reply=result["reply"],
            session_id=result["session_id"],
            status=result.get("status", "active"),
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")
