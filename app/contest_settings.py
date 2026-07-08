from sqlalchemy.orm import Session

from app.models import ContestSettings

SETTINGS_ID = 1

DEFAULT_RULES_TEXT = "主辦單位尚未設定比賽辦法內容,請聯絡管理員。"


def get_or_create_settings(db: Session) -> ContestSettings:
    settings = db.get(ContestSettings, SETTINGS_ID)
    if not settings:
        settings = ContestSettings(id=SETTINGS_ID, rules_text=None)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
