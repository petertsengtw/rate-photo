from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, SECURE_COOKIES, SESSION_MAX_AGE
from app.database import get_db
from app.models import AdminUser, Judge
from app.security import constant_time_compare, generate_csrf_token

ADMIN_COOKIE_NAME = "admin_session"
JUDGE_COOKIE_NAME = "judge_session"
CSRF_COOKIE_NAME = "csrf_token"

_admin_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="admin-session")
_judge_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="judge-session")


def _set_session_cookie(response: Response, name: str, serializer: URLSafeTimedSerializer, payload: dict) -> None:
    token = serializer.dumps(payload)
    response.set_cookie(
        key=name,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
    )


def _read_session(request: Request, name: str, serializer: URLSafeTimedSerializer) -> dict | None:
    raw = request.cookies.get(name)
    if not raw:
        return None
    try:
        return serializer.loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_admin_session(response: Response, admin_id: int) -> None:
    _set_session_cookie(response, ADMIN_COOKIE_NAME, _admin_serializer, {"admin_id": admin_id})


def set_judge_session(response: Response, judge_id: int) -> None:
    _set_session_cookie(response, JUDGE_COOKIE_NAME, _judge_serializer, {"judge_id": judge_id})


def clear_admin_session(response: Response) -> None:
    response.delete_cookie(ADMIN_COOKIE_NAME)


def clear_judge_session(response: Response) -> None:
    response.delete_cookie(JUDGE_COOKIE_NAME)


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token:
        token = generate_csrf_token()
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            httponly=False,
            samesite="lax",
            secure=SECURE_COOKIES,
        )
    return token


async def verify_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    submitted = request.headers.get("X-CSRF-Token")
    if not submitted:
        content_type = request.headers.get("content-type", "")
        if "form" in content_type:
            form = await request.form()
            submitted = form.get("csrf_token")
    if not cookie_token or not submitted or not constant_time_compare(cookie_token, submitted):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token 驗證失敗,請重新整理頁面後再試一次")


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    session = _read_session(request, ADMIN_COOKIE_NAME, _admin_serializer)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入管理員帳號")
    admin = db.get(AdminUser, session["admin_id"])
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入管理員帳號")
    return admin


def require_admin_write(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if admin.is_readonly:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="此帳號為唯讀權限,無法執行此操作")
    return admin


def get_current_admin_optional(request: Request, db: Session = Depends(get_db)) -> AdminUser | None:
    session = _read_session(request, ADMIN_COOKIE_NAME, _admin_serializer)
    if not session:
        return None
    return db.get(AdminUser, session["admin_id"])


def get_current_judge(request: Request, db: Session = Depends(get_db)) -> Judge:
    session = _read_session(request, JUDGE_COOKIE_NAME, _judge_serializer)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入評審帳號")
    judge = db.get(Judge, session["judge_id"])
    if not judge:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入評審帳號")
    return judge


def require_judge_agreed(judge: Judge = Depends(get_current_judge)) -> Judge:
    if judge.agreed_at is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="請先閱讀並同意比賽辦法")
    return judge


def get_current_judge_optional(request: Request, db: Session = Depends(get_db)) -> Judge | None:
    session = _read_session(request, JUDGE_COOKIE_NAME, _judge_serializer)
    if not session:
        return None
    return db.get(Judge, session["judge_id"])
