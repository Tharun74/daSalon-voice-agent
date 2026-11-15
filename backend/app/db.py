import json
import threading
import os
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from bson import ObjectId
import pymongo
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app import config

logger = logging.getLogger("dasalon.db")

_client: Optional[Any] = None
_db: Optional[Any] = None
_is_mock: bool = False
_persist_lock = threading.RLock()


def _json_serial(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return {"$datetime": obj.isoformat()}
    if isinstance(obj, ObjectId):
        return {"$oid": str(obj)}
    raise TypeError(f"Type {type(obj)} not serializable")


def _json_deserial(dct: Dict[str, Any]) -> Any:
    """JSON deserializer for custom types"""
    if "$datetime" in dct:
        return datetime.fromisoformat(dct["$datetime"])
    if "$oid" in dct:
        return ObjectId(dct["$oid"])
    return dct


def get_client() -> pymongo.MongoClient:
    """Get or initialize MongoDB client with graceful fallback."""
    global _client, _db, _is_mock
    if _client is not None:
        return _client

    use_mock = config.MONGODB_URI.startswith("mongomock://")
    if not use_mock:
        try:
            client = pymongo.MongoClient(
                config.MONGODB_URI,
                serverSelectionTimeoutMS=800,
                connectTimeoutMS=800,
                socketTimeoutMS=800,
            )
            client.admin.command("ping")
            _client = client
            _db = _client[config.MONGODB_DB]
            _is_mock = False
            logger.info(f"Connected to live MongoDB at {config.MONGODB_URI}")
            return _client
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            logger.warning(
                f"Could not connect to MongoDB at {config.MONGODB_URI}: {e}. "
                "Falling back to disk-persisted mongomock for local development."
            )
            use_mock = True

    if use_mock:
        import mongomock

        _client = mongomock.MongoClient()
        _db = _client[config.MONGODB_DB]
        _is_mock = True
        _load_mock_backup()
        logger.info("Initialized mongomock fallback.")

    return _client


def get_db():
    """Get database instance."""
    if _db is None:
        get_client()
    return _db


def is_mock_db() -> bool:
    """Check if running against mock DB."""
    if _db is None:
        get_client()
    return _is_mock


def _load_mock_backup():
    """Load mock data from disk if exists."""
    if not config.MONGO_BACKUP_FILE.exists():
        return
    try:
        with open(config.MONGO_BACKUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f, object_hook=_json_deserial)
            for coll_name, docs in data.items():
                if docs:
                    _db[coll_name].insert_many(docs)
    except Exception as e:
        logger.error(f"Error loading mock backup: {e}")


def persist_mock_data():
    """Save mock data to disk so seed persists across processes."""
    if not _is_mock or _db is None:
        return
    try:
        collections = [
            "salons",
            "bot_configs",
            "services",
            "staff",
            "offers",
            "appointments",
            "conversations",
            "handoffs",
            "unanswered_questions",
            "documents",
            "voice_usage",
            "booking_requests",
        ]
        with _persist_lock:
            data = {name: list(_db[name].find()) for name in collections}
            temporary = config.MONGO_BACKUP_FILE.with_suffix('.tmp')
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(data, f, default=_json_serial, indent=2)
            os.replace(temporary, config.MONGO_BACKUP_FILE)
    except Exception as e:
        logger.error(f"Error persisting mock backup: {e}")


def create_indexes():
    """Create essential MongoDB indexes."""
    db = get_db()
    try:
        # salons
        db.salons.create_index("_id")

        # bot_configs
        db.bot_configs.create_index("salon_id", unique=True)

        # services
        db.services.create_index("salon_id")
        db.services.create_index([("salon_id", 1), ("category", 1)])

        # staff
        db.staff.create_index("salon_id")

        # offers
        db.offers.create_index("salon_id")

        # appointments
        db.appointments.create_index("salon_id")
        db.appointments.create_index([("salon_id", 1), ("start_time", 1)])
        db.appointments.create_index([("salon_id", 1), ("phone", 1)])

        # conversations
        db.conversations.create_index([("salon_id", 1), ("session_id", 1)])

        # handoffs
        db.handoffs.create_index("salon_id")
        db.handoffs.create_index([("salon_id", 1), ("status", 1)])

        # unanswered_questions
        db.unanswered_questions.create_index([("salon_id", 1), ("question", 1)])

        # documents
        db.documents.create_index([("salon_id", 1), ("doc_id", 1)])
    except Exception as e:
        logger.warning(f"Index creation notice: {e}")


def serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert Mongo document to JSON serializable dict."""
    if doc is None:
        return None
    res = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            res[k] = str(v)
        elif isinstance(v, (datetime, date)):
            res[k] = v.isoformat()
        elif isinstance(v, list):
            res[k] = [serialize_doc(item) if isinstance(item, dict) else item for item in v]
        elif isinstance(v, dict):
            res[k] = serialize_doc(v)
        else:
            res[k] = v
    return res


def serialize_list(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert list of Mongo documents."""
    return [serialize_doc(d) for d in docs]
