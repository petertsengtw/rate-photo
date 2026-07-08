import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.config import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_FORMATS, MAX_UPLOAD_SIZE, UPLOAD_DIR


def save_photo_upload(file: UploadFile) -> str:
    """Validate and persist an uploaded image. Returns the stored filename."""
    original_name = file.filename or ""
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的檔案類型:{ext or '未知'},僅接受 jpg/png/webp",
        )

    contents = file.file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="檔案過大,單檔上限為 10MB",
        )
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="檔案是空的")

    import io

    try:
        image = Image.open(io.BytesIO(contents))
        image.verify()
        image_format = image.format
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="檔案內容不是有效的圖片") from None

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的圖片格式:{image_format},僅接受 JPEG/PNG/WEBP",
        )

    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = UPLOAD_DIR / stored_name
    dest_path.write_bytes(contents)
    return stored_name


def delete_photo_file(stored_name: str) -> None:
    path = UPLOAD_DIR / stored_name
    if path.exists():
        path.unlink()
