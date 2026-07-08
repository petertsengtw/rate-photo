"""Create or reset an admin account.

Usage:
    python -m scripts.create_admin <username> <password> [--readonly] [--force-weak-password]
"""

import sys

from app.database import Base, SessionLocal, apply_sqlite_column_migrations, engine
from app.models import AdminUser
from app.security import hash_password


def main() -> None:
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    positional = [a for a in args if not a.startswith("--")]

    if len(positional) != 2:
        print("Usage: python -m scripts.create_admin <username> <password> [--readonly] [--force-weak-password]")
        raise SystemExit(1)

    username, password = positional
    is_readonly = "--readonly" in flags
    force_weak = "--force-weak-password" in flags

    if len(password) < 8 and not force_weak:
        print("密碼長度至少需要 8 個字元(若確定要用較弱的密碼,加上 --force-weak-password)")
        raise SystemExit(1)

    Base.metadata.create_all(bind=engine)
    apply_sqlite_column_migrations()
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter_by(username=username).first()
        if admin:
            admin.password_hash = hash_password(password)
            admin.is_readonly = is_readonly
            print(f"已更新管理員 '{username}' 的密碼(唯讀:{is_readonly})")
        else:
            admin = AdminUser(username=username, password_hash=hash_password(password), is_readonly=is_readonly)
            db.add(admin)
            print(f"已建立管理員帳號 '{username}'(唯讀:{is_readonly})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
