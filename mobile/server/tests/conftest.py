"""Run the API tests against a throwaway SQLite file, not the dev server's DB."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PRICES_DB_PATH", str(Path(tempfile.mkdtemp(prefix="ml-api-test-")) / "prices.db"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
