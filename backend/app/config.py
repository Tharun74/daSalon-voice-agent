import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "accounts/fireworks/models/gpt-oss-120b")
MONGODB_URI = "mongomock://localhost"  # Isolated local demo data, never the original Partner database.
MONGODB_DB = os.getenv("MONGODB_DB", "dasalon")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# Storage paths
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
CHROMA_DIR = DATA_DIR / "chroma"
UPLOADS_DIR = DATA_DIR / "uploads"
MONGO_BACKUP_FILE = DATA_DIR / "mongo_state.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
