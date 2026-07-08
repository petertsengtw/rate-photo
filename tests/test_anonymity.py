from app.models import AdminUser, Criteria, Group, Judge, Photo
from app.security import hash_password, generate_token


def _seed(db_session):
    admin = AdminUser(username="admin", password_hash=hash_password("adminpass123"))
    db_session.add(admin)

    c1 = Criteria(name="構圖", weight=30, sort_order=0)
    c2 = Criteria(name="主題契合度", weight=40, sort_order=1)
    c3 = Criteria(name="創意", weight=30, sort_order=2)
    db_session.add_all([c1, c2, c3])

    judge1 = Judge(
        name="秘密評審A",
        username="judge_secret_a",
        password_hash=hash_password("passwordA123"),
        token=generate_token(),
    )
    judge2 = Judge(
        name="秘密評審B",
        username="judge_secret_b",
        password_hash=hash_password("passwordB123"),
        token=generate_token(),
    )
    db_session.add_all([judge1, judge2])
    db_session.commit()

    staff_group = db_session.query(Group).filter_by(code="staff").first()
    photo = Photo(
        group_id=staff_group.id,
        code="001",
        image_path="does-not-need-to-exist.jpg",
        submitter_note="投稿者真實姓名:王小明",
    )
    db_session.add(photo)
    db_session.commit()
    return {"judge1": judge1, "judge2": judge2, "photo": photo, "criteria": [c1, c2, c3]}


def test_unauthenticated_requests_redirect_to_login(client):
    r = client.get("/admin/criteria", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login"

    r = client.get("/judge/groups", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/judge/login"


def test_judge_link_login_hides_other_judges_and_submitter_note(client, db_session):
    seeded = _seed(db_session)
    judge1 = seeded["judge1"]
    judge2 = seeded["judge2"]
    photo = seeded["photo"]

    r = client.get(f"/judge/link/{judge1.token}", follow_redirects=True)
    assert r.status_code == 200

    groups_html = client.get("/judge/groups").text
    assert judge2.name not in groups_html
    assert judge2.username not in groups_html
    assert judge1.username not in groups_html  # judge shouldn't see their own username listed either

    photos_html = client.get("/judge/photos?group=staff").text
    assert judge2.name not in photos_html
    assert "王小明" not in photos_html

    score_page_html = client.get(f"/judge/photos/{photo.id}").text
    assert "王小明" not in score_page_html
    assert "submitter_note" not in score_page_html
    assert judge2.name not in score_page_html
    assert judge2.username not in score_page_html


def test_csrf_required_for_mutating_requests(client, db_session):
    _seed(db_session)
    client.get("/admin/login")  # obtain csrf cookie
    csrf = client.cookies.get("csrf_token")
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "adminpass123", "csrf_token": csrf},
    )
    r = client.post("/admin/criteria", data={"name": "test", "weight": "10"})
    assert r.status_code == 403


def test_score_submission_and_weighted_total(client, db_session):
    seeded = _seed(db_session)
    judge1 = seeded["judge1"]
    photo = seeded["photo"]
    criteria = seeded["criteria"]

    client.get(f"/judge/link/{judge1.token}", follow_redirects=True)
    client.get(f"/judge/photos/{photo.id}")  # ensure csrf cookie present
    csrf = client.cookies.get("csrf_token")

    form = {"csrf_token": csrf}
    values = {criteria[0].id: 8, criteria[1].id: 7, criteria[2].id: 9}
    for cid, val in values.items():
        form[f"score_{cid}"] = str(val)

    r = client.post(f"/judge/photos/{photo.id}/score", data=form, follow_redirects=False)
    assert r.status_code == 303

    detail_html = client.get(f"/judge/photos/{photo.id}").text
    assert 'value="8"' in detail_html
    assert 'value="7"' in detail_html
    assert 'value="9"' in detail_html
    # (8*30 + 7*40 + 9*30) / 100 = 7.9
    assert "7.9" in detail_html


def test_login_rate_limiting(client, db_session):
    _seed(db_session)
    client.get("/judge/login")
    csrf = client.cookies.get("csrf_token")
    last_status = None
    for _ in range(6):
        last_status = client.post(
            "/judge/login",
            data={"username": "judge_secret_a", "password": "wrongpassword", "csrf_token": csrf},
        ).status_code
    assert last_status == 429
