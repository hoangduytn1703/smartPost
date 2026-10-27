import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

STORAGE_DIR = Path(os.environ.get("SMARTPOST_STORAGE", ROOT / "storage"))
JOBS_DIR = STORAGE_DIR / "jobs"
DB_PATH = STORAGE_DIR / "smartpost.db"
FRONTEND_DIST = ROOT / "frontend" / "dist"

HOST = os.environ.get("SMARTPOST_HOST", "0.0.0.0")
PORT = int(os.environ.get("SMARTPOST_PORT", "8500"))

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")


def gemini_keys() -> list[str]:
    raw = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


FETCH_PARALLEL = int(os.environ.get("SMARTPOST_FETCH_PARALLEL", "2"))
PLAN_PARALLEL = int(os.environ.get("SMARTPOST_PLAN_PARALLEL", "3"))
RENDER_PARALLEL = int(os.environ.get("SMARTPOST_RENDER_PARALLEL", "2"))
YTDLP_ARGS = os.environ.get("SMARTPOST_YTDLP_ARGS", "").split()


def job_dir(job_id: int) -> Path:
    path = JOBS_DIR / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
