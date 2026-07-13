import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    clear_judge_session,
    ensure_csrf_cookie,
    get_current_judge,
    require_judge_agreed,
    set_judge_session,
    verify_csrf,
)
from app.config import SCORE_MAX, SCORE_MIN
from app.contest_settings import get_or_create_settings
from app.database import get_db
from app.models import Criteria, Group, Judge, Photo, Score
from app.models import utcnow as _utcnow
from app.render import templates
from app.scoring import compute_weighted_total, parse_criteria_json
from app.security import login_rate_limiter, verify_password

router = APIRouter(prefix="/judge", tags=["judge"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _apply_cookies(tmpl_response, response: Response):
    tmpl_response.headers.raw.extend(response.raw_headers)
    return tmpl_response


# ---------- Auth ----------


@router.get("/login")
def login_form(request: Request, response: Response):
    csrf_token = ensure_csrf_cookie(request, response)
    tmpl_response = templates.TemplateResponse(
        request, "judge/login.html", {"csrf_token": csrf_token, "error": None}
    )
    return _apply_cookies(tmpl_response, response)


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    ip = _client_ip(request)
    if login_rate_limiter.is_locked("judge_login", ip):
        wait = login_rate_limiter.seconds_until_unlock("judge_login", ip)
        return templates.TemplateResponse(
            request,
            "judge/login.html",
            {"csrf_token": csrf_token, "error": f"登入失敗次數過多,請於 {wait} 秒後再試"},
            status_code=429,
        )

    judge = db.query(Judge).filter_by(username=username).first()
    if not judge or not verify_password(password, judge.password_hash):
        login_rate_limiter.record_failure("judge_login", ip)
        return templates.TemplateResponse(
            request, "judge/login.html", {"csrf_token": csrf_token, "error": "帳號或密碼錯誤"}, status_code=401
        )

    login_rate_limiter.record_success("judge_login", ip)
    redirect = RedirectResponse(url="/judge/groups", status_code=303)
    set_judge_session(redirect, judge.id)
    return redirect


@router.get("/link/{token}")
def login_via_link(token: str, db: Session = Depends(get_db)):
    judge = db.query(Judge).filter_by(token=token).first()
    if not judge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="連結無效")
    redirect = RedirectResponse(url="/judge/groups", status_code=303)
    set_judge_session(redirect, judge.id)
    return redirect


@router.post("/logout")
async def logout(request: Request):
    await verify_csrf(request)
    redirect = RedirectResponse(url="/judge/login", status_code=303)
    clear_judge_session(redirect)
    return redirect


# ---------- Contest rules agreement ----------


@router.get("/agreement")
def agreement_form(
    request: Request,
    response: Response,
    judge: Judge = Depends(get_current_judge),
    db: Session = Depends(get_db),
):
    csrf_token = ensure_csrf_cookie(request, response)
    if judge.agreed_at is not None:
        return RedirectResponse(url="/judge/groups", status_code=303)
    settings = get_or_create_settings(db)
    tmpl_response = templates.TemplateResponse(
        request,
        "judge/agreement.html",
        {"rules_text": settings.rules_text, "csrf_token": csrf_token, "error": None},
    )
    return _apply_cookies(tmpl_response, response)


@router.post("/agreement")
async def agreement_submit(
    request: Request,
    agree: str = Form(""),
    judge: Judge = Depends(get_current_judge),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    if agree != "yes":
        settings = get_or_create_settings(db)
        csrf_token = request.cookies.get("csrf_token", "")
        return templates.TemplateResponse(
            request,
            "judge/agreement.html",
            {
                "rules_text": settings.rules_text,
                "csrf_token": csrf_token,
                "error": "請先勾選「我已閱讀並同意」才能開始評分",
            },
            status_code=400,
        )
    judge.agreed_at = _utcnow()
    db.commit()
    return RedirectResponse(url="/judge/groups", status_code=303)


# ---------- Groups & photo list ----------


@router.get("/groups")
def groups_page(
    request: Request,
    response: Response,
    judge: Judge = Depends(require_judge_agreed),
    db: Session = Depends(get_db),
):
    csrf_token = ensure_csrf_cookie(request, response)
    groups = db.query(Group).order_by(Group.id).all()
    summary = []
    total_all = 0
    scored_all = 0
    for g in groups:
        total = db.query(Photo).filter_by(group_id=g.id).count()
        scored = (
            db.query(Score)
            .join(Photo, Score.photo_id == Photo.id)
            .filter(Photo.group_id == g.id, Score.judge_id == judge.id)
            .count()
        )
        summary.append({"group": g, "total": total, "scored": scored})
        total_all += total
        scored_all += scored

    all_scored = total_all > 0 and total_all == scored_all
    tmpl_response = templates.TemplateResponse(
        request,
        "judge/groups.html",
        {
            "summary": summary,
            "csrf_token": csrf_token,
            "all_scored": all_scored,
            "submitted": judge.submitted_at is not None,
        },
    )
    return _apply_cookies(tmpl_response, response)


@router.post("/submit")
async def submit_final(
    request: Request,
    judge: Judge = Depends(require_judge_agreed),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    if judge.submitted_at is not None:
        return RedirectResponse(url="/judge/groups", status_code=303)

    total_all = db.query(Photo).count()
    scored_all = db.query(Score).filter_by(judge_id=judge.id).count()
    if total_all == 0 or scored_all < total_all:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="尚有照片未評分,無法送出")

    judge.submitted_at = _utcnow()
    db.commit()
    return RedirectResponse(url="/judge/groups", status_code=303)


@router.get("/photos")
def photos_list(
    request: Request,
    response: Response,
    group: str = "staff",
    judge: Judge = Depends(require_judge_agreed),
    db: Session = Depends(get_db),
):
    csrf_token = ensure_csrf_cookie(request, response)
    groups = db.query(Group).order_by(Group.id).all()
    group_obj = db.query(Group).filter_by(code=group).first()
    if not group_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到組別")
    photos = db.query(Photo).filter_by(group_id=group_obj.id).order_by(Photo.code).all()
    my_scores = {
        s.photo_id: s
        for s in db.query(Score).filter(Score.judge_id == judge.id, Score.photo_id.in_([p.id for p in photos])).all()
    }
    photo_rows = [
        {"photo": p, "scored": p.id in my_scores, "weighted_total": my_scores[p.id].weighted_total if p.id in my_scores else None}
        for p in photos
    ]
    tmpl_response = templates.TemplateResponse(
        request,
        "judge/photos.html",
        {
            "groups": groups,
            "group": group_obj,
            "photo_rows": photo_rows,
            "csrf_token": csrf_token,
            "locked": judge.submitted_at is not None,
        },
    )
    return _apply_cookies(tmpl_response, response)


# ---------- Scoring ----------


@router.get("/photos/{photo_id}")
def photo_detail(
    photo_id: int,
    request: Request,
    response: Response,
    judge: Judge = Depends(require_judge_agreed),
    db: Session = Depends(get_db),
):
    csrf_token = ensure_csrf_cookie(request, response)
    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到照片")
    criteria = db.query(Criteria).order_by(Criteria.sort_order, Criteria.id).all()
    existing_score = db.query(Score).filter_by(judge_id=judge.id, photo_id=photo.id).first()
    existing_values = parse_criteria_json(existing_score.criteria_json) if existing_score else {}

    tmpl_response = templates.TemplateResponse(
        request,
        "judge/score.html",
        {
            "photo": photo,
            "criteria": criteria,
            "existing_values": existing_values,
            "existing_total": existing_score.weighted_total if existing_score else None,
            "existing_comment": existing_score.comment if existing_score else "",
            "csrf_token": csrf_token,
            "score_min": SCORE_MIN,
            "score_max": SCORE_MAX,
            "group_code": photo.group.code,
            "locked": judge.submitted_at is not None,
        },
    )
    return _apply_cookies(tmpl_response, response)


@router.post("/photos/{photo_id}/score")
async def submit_score(
    photo_id: int,
    request: Request,
    judge: Judge = Depends(require_judge_agreed),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    if judge.submitted_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您已完成並送出評分,無法再修改")

    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到照片")

    criteria = db.query(Criteria).order_by(Criteria.sort_order, Criteria.id).all()
    form = await request.form()
    criteria_scores: dict[str, int] = {}
    for c in criteria:
        raw_value = form.get(f"score_{c.id}")
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"「{c.name}」分數必須為整數")
        if value < SCORE_MIN or value > SCORE_MAX:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"「{c.name}」分數需介於 {SCORE_MIN} 到 {SCORE_MAX} 之間",
            )
        criteria_scores[c.name] = value

    comment = str(form.get("comment", "")).strip() or None
    weighted_total = compute_weighted_total(criteria_scores, criteria)

    existing = db.query(Score).filter_by(judge_id=judge.id, photo_id=photo.id).first()
    if existing:
        existing.criteria_json = json.dumps(criteria_scores, ensure_ascii=False)
        existing.weighted_total = weighted_total
        existing.comment = comment
    else:
        db.add(
            Score(
                judge_id=judge.id,
                photo_id=photo.id,
                criteria_json=json.dumps(criteria_scores, ensure_ascii=False),
                weighted_total=weighted_total,
                comment=comment,
            )
        )
    db.commit()

    return RedirectResponse(url=f"/judge/photos?group={photo.group.code}&saved={photo.code}", status_code=303)
