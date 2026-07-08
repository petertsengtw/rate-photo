import os
import secrets
from pathlib import Path

BASE_DIR = Path(os.environ.get("PHOTO_CONTEST_HOME", Path(__file__).resolve().parent.parent))

DATABASE_URL = os.environ.get("PHOTO_CONTEST_DATABASE_URL", f"sqlite:///{BASE_DIR / 'data.db'}")

UPLOAD_DIR = Path(os.environ.get("PHOTO_CONTEST_UPLOAD_DIR", BASE_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

SESSION_MAX_AGE = 8 * 60 * 60  # 8 hours

# Set to "0" only for local HTTP development/testing. Production behind
# Caddy HTTPS must keep this true so session/CSRF cookies require TLS.
SECURE_COOKIES = os.environ.get("PHOTO_CONTEST_SECURE_COOKIES", "1") == "1"

_secret_key_file = Path(os.environ.get("PHOTO_CONTEST_SECRET_KEY_FILE", BASE_DIR / ".secret_key"))


def _load_or_create_secret_key() -> str:
    if _secret_key_file.exists():
        return _secret_key_file.read_text().strip()
    key = secrets.token_hex(32)
    _secret_key_file.write_text(key)
    _secret_key_file.chmod(0o600)
    return key


SECRET_KEY = os.environ.get("PHOTO_CONTEST_SECRET_KEY") or _load_or_create_secret_key()

# Login rate limiting
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60
LOGIN_WINDOW_SECONDS = 300

SCORE_MIN = 1
SCORE_MAX = 10

# Tie-break threshold: a judge's per-photo weighted score at or above this
# counts as a "top mark" when resolving ties in the results ranking.
HIGH_SCORE_THRESHOLD = 9
