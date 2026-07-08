import secrets
import time
from collections import defaultdict

import bcrypt

from app.config import LOGIN_LOCKOUT_SECONDS, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_SECONDS


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def generate_token(n_bytes: int = 24) -> str:
    return secrets.token_urlsafe(n_bytes)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_compare(a: str, b: str) -> bool:
    return secrets.compare_digest(a or "", b or "")


class LoginRateLimiter:
    """In-memory sliding-window rate limiter, keyed by (bucket, ip).

    Sufficient for a single-process deployment with <=10 concurrent users,
    as specified by the SDD's non-functional requirements. Not shared across
    multiple worker processes.
    """

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._locked_until: dict[tuple[str, str], float] = {}

    def _key(self, bucket: str, ip: str) -> tuple[str, str]:
        return (bucket, ip)

    def is_locked(self, bucket: str, ip: str) -> bool:
        key = self._key(bucket, ip)
        until = self._locked_until.get(key)
        if until is None:
            return False
        if time.time() >= until:
            del self._locked_until[key]
            return False
        return True

    def seconds_until_unlock(self, bucket: str, ip: str) -> int:
        key = self._key(bucket, ip)
        until = self._locked_until.get(key, 0)
        return max(0, int(until - time.time()))

    def record_failure(self, bucket: str, ip: str) -> None:
        key = self._key(bucket, ip)
        now = time.time()
        window_start = now - LOGIN_WINDOW_SECONDS
        attempts = [t for t in self._attempts[key] if t >= window_start]
        attempts.append(now)
        self._attempts[key] = attempts
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            self._locked_until[key] = now + LOGIN_LOCKOUT_SECONDS
            self._attempts[key] = []

    def record_success(self, bucket: str, ip: str) -> None:
        key = self._key(bucket, ip)
        self._attempts.pop(key, None)
        self._locked_until.pop(key, None)


login_rate_limiter = LoginRateLimiter()
