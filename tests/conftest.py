import os
import tempfile

_tmp_home = tempfile.mkdtemp(prefix="photo_contest_test_")
os.environ["PHOTO_CONTEST_HOME"] = _tmp_home
os.environ["PHOTO_CONTEST_SECURE_COOKIES"] = "0"

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from app.database import Base, engine
    from app.main import app

    Base.metadata.drop_all(bind=engine)
    with TestClient(app, base_url="http://testserver") as c:
        yield c


@pytest.fixture()
def db_session(client):
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
