from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_sqlite_column_migrations() -> None:
    """Add columns introduced after a database file was first created.

    SQLite's `CREATE TABLE IF NOT EXISTS` (used by Base.metadata.create_all)
    never adds columns to an existing table, so new nullable columns need a
    one-off ALTER TABLE here. Kept intentionally simple (no Alembic) to match
    the SDD's single-contest, low-maintenance scope.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        existing_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(photos)"))}
        if "caption" not in existing_columns:
            conn.execute(text("ALTER TABLE photos ADD COLUMN caption TEXT"))
            conn.commit()
        if "title" not in existing_columns:
            conn.execute(text("ALTER TABLE photos ADD COLUMN title VARCHAR"))
            conn.commit()

        admin_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(admin_users)"))}
        if "is_readonly" not in admin_columns:
            conn.execute(text("ALTER TABLE admin_users ADD COLUMN is_readonly BOOLEAN NOT NULL DEFAULT 0"))
            conn.commit()
