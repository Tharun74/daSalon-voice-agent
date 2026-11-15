import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app import config
from app.db import get_client, get_db, is_mock_db, create_indexes
from app.routes.salons import router as salons_router
from app.routes.chat_routes import router as chat_router
from app.routes.docs_routes import router as docs_router
from app.routes.admin_routes import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dasalon")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing da Salon Bot platform...")
    create_indexes()
    from app.demo_seed import ensure_demo
    ensure_demo()
    try:
        from app.voice.routes import warmup_voice_cache
        await warmup_voice_cache()
    except Exception as e:
        logger.warning(f"Voice cache warmup skipped: {e}")
    yield
    logger.info("Shutting down da Salon Bot platform...")


app = FastAPI(
    title="da Salon Multi-Tenant AI Platform",
    description="Multi-tenant salon & spa AI assistant demo",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=__import__("os").getenv("VOICE_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import RedirectResponse

# Include routers
app.include_router(salons_router)
app.include_router(chat_router)
app.include_router(docs_router)
app.include_router(admin_router)
from app.voice.routes import router as voice_router
from app.voice.ws import router as voice_ws_router
app.include_router(voice_router)
app.include_router(voice_ws_router)
from app.demo_auth import router as demo_router
from app.partner_api import router as partner_router
app.include_router(demo_router)
app.include_router(partner_router)

@app.middleware("http")
async def bound_voice_upload(request, call_next):
    # Bound body before multipart parsing, so oversized audio is never spooled to disk.
    if request.url.path == "/voice/turn":
        from app.voice.session import MAX_BYTES
        from fastapi.responses import JSONResponse
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES + 16384:
                return JSONResponse({"detail": "Voice upload too large"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
    return await call_next(request)


# Mount static files
static_dir = config.BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def add_dev_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
def health():
    """Health check endpoint checking Mongo connection."""
    db = get_db()
    try:
        if is_mock_db():
            mongo_status = "connected (in-memory persistent fallback)"
        else:
            get_client().admin.command("ping")
            mongo_status = "connected"
    except Exception as e:
        mongo_status = f"error: {str(e)}"

    return {
        "status": "ok" if "connected" in mongo_status else "degraded",
        "mongodb": mongo_status,
        "database": config.MONGODB_DB,
        "model": config.LLM_MODEL,
        "timezone": config.TIMEZONE,
    }
