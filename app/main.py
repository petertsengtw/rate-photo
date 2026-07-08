import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, SessionLocal, apply_sqlite_column_migrations, engine
from app.models import AdminUser, Group

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("photo_contest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_sqlite_column_migrations()
    db = SessionLocal()
    try:
        if not db.query(Group).filter_by(code="staff").first():
            db.add(Group(code="staff", name="同仁組"))
        if not db.query(Group).filter_by(code="public").first():
            db.add(Group(code="public", name="社會組"))
        db.commit()
        admin_count = db.query(AdminUser).count()
        if admin_count == 0:
            logger.warning(
                "尚未建立任何管理員帳號,請執行 `python -m scripts.create_admin` 建立第一個管理員帳號。"
            )
    finally:
        db.close()
    yield


app = FastAPI(title="攝影比賽線上評分系統", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.info("HTTPException %s on %s: %s", exc.status_code, request.url.path, exc.detail)
    if exc.status_code == 401:
        if request.url.path.startswith("/admin"):
            return RedirectResponse(url="/admin/login", status_code=303)
        if request.url.path.startswith("/judge"):
            return RedirectResponse(url="/judge/login", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "伺服器發生錯誤,請稍後再試或聯絡管理員"})


@app.get("/")
def root():
    return RedirectResponse(url="/judge/login")


from app.routers import admin, judge, media  # noqa: E402

app.include_router(admin.router)
app.include_router(judge.router)
app.include_router(media.router)
