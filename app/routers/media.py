from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_admin_optional, get_current_judge_optional
from app.config import UPLOAD_DIR
from app.database import get_db
from app.models import Photo

router = APIRouter(tags=["media"])


@router.get("/media/{filename}")
def get_media(filename: str, request: Request, db: Session = Depends(get_db)):
    admin = get_current_admin_optional(request, db)
    judge = get_current_judge_optional(request, db)
    if not admin and not judge:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入")

    photo = db.query(Photo).filter(Photo.image_path == filename).first()
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到圖片")

    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到圖片")
    return FileResponse(path)
