import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Tests must never seed or write the developer's configured database.
import os
import tempfile
os.environ["MONGODB_URI"] = "mongomock://localhost"
os.environ["FIREWORKS_API_KEY"] = ""
os.environ["SARVAM_API_KEY"] = ""
from app import config
_test_dir = tempfile.TemporaryDirectory(prefix="dasalon-tests-", ignore_cleanup_errors=True)
config.MONGO_BACKUP_FILE = Path(_test_dir.name) / "mongo.json"
config.CHROMA_DIR = Path(_test_dir.name) / "chroma"

import pytest
from app.seed import seed_database
from app.db import get_db

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    seed_database()
    yield
