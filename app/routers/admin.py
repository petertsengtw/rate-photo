import csv
import io
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth import (
    clear_admin_session,
    ensure_csrf_cookie,
    get_current_admin,
    require_admin_write,
    set_admin_session,
    verify_csrf,
)
from app.config import DATABASE_URL, HIGH_SCORE_THRESHOLD
from app.database import get_db
from app.models import AdminUser, Criteria, Group, Judge, Photo, Score
from app.render import templates
from app.security import (
    generate_token,
    hash_password,
    login_rate_limiter,
    verify_password,
)
from app.uploads import delete_photo_file, save_photo_upload

router = APIRouter(prefix="/admin", tags=["admin"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- Auth ----------


@router.get("/login")
def login_form(request: Request, response: Response):
    csrf_token = ensure_csrf_cookie(request, response)
    tmpl_response = templates.TemplateResponse(
        request, "admin/login.html", {"csrf_token": csrf_token, "error": None}
    )
    tmpl_response.headers.raw.extend(response.raw_headers)
    return tmpl_response


@router.post("/login")
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    ip = _client_ip(request)
    if login_rate_limiter.is_locked("admin_login", ip):
        wait = login_rate_limiter.seconds_until_unlock("admin_login", ip)
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"csrf_token": csrf_token, "error": f"登入失敗次數過多,請於 {wait} 秒後再試"},
            status_code=429,
        )

    admin = db.query(AdminUser).filter_by(username=username).first()
    if not admin or not verify_password(password, admin.password_hash):
        login_rate_limiter.record_failure("admin_login", ip)
        return templates.TemplateResponse(
            request, "admin/login.html", {"csrf_token": csrf_token, "error": "帳號或密碼錯誤"}, status_code=401
        )

    login_rate_limiter.record_success("admin_login", ip)
    redirect = RedirectResponse(url="/admin/criteria", status_code=303)
    set_admin_session(redirect, admin.id)
    return redirect


@router.post("/logout")
async def logout(request: Request):
    await verify_csrf(request)
    redirect = RedirectResponse(url="/admin/login", status_code=303)
    clear_admin_session(redirect)
    return redirect


# ---------- Criteria ----------


@router.get("/criteria")
def criteria_page(request: Request, response: Response, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    csrf_token = ensure_csrf_cookie(request, response)
    criteria = db.query(Criteria).order_by(Criteria.sort_order, Criteria.id).all()
    total_weight = sum(c.weight for c in criteria)
    tmpl_response = templates.TemplateResponse(
        request,
        "admin/criteria.html",
        {"criteria": criteria, "total_weight": total_weight, "csrf_token": csrf_token, "admin": admin},
    )
    tmpl_response.headers.raw.extend(response.raw_headers)
    return tmpl_response


@router.post("/criteria")
async def create_criteria(
    request: Request,
    name: str = Form(...),
    weight: int = Form(...),
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    if weight <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="權重必須大於 0")
    max_order = db.query(Criteria).count()
    db.add(Criteria(name=name.strip(), weight=weight, sort_order=max_order))
    db.commit()
    return RedirectResponse(url="/admin/criteria", status_code=303)


@router.delete("/criteria/{criteria_id}")
async def delete_criteria(
    criteria_id: int,
    request: Request,
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    criteria = db.get(Criteria, criteria_id)
    if not criteria:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到評分項目")
    db.delete(criteria)
    db.commit()
    return {"ok": True}


# ---------- Judges ----------


@router.get("/judges")
def judges_page(request: Request, response: Response, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    csrf_token = ensure_csrf_cookie(request, response)
    judges = db.query(Judge).order_by(Judge.id).all()
    judge_links = {}
    if not admin.is_readonly:
        base_url = str(request.base_url).rstrip("/")
        judge_links = {j.id: f"{base_url}/judge/link/{j.token}" for j in judges}
    tmpl_response = templates.TemplateResponse(
        request,
        "admin/judges.html",
        {"judges": judges, "judge_links": judge_links, "csrf_token": csrf_token, "admin": admin},
    )
    tmpl_response.headers.raw.extend(response.raw_headers)
    return tmpl_response


@router.post("/judges")
async def create_judge(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    if db.query(Judge).filter_by(username=username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="帳號已被使用")
    judge = Judge(
        name=name.strip(),
        username=username.strip(),
        password_hash=hash_password(password),
        token=generate_token(),
    )
    db.add(judge)
    db.commit()
    return RedirectResponse(url="/admin/judges", status_code=303)


@router.delete("/judges/{judge_id}")
async def delete_judge(
    judge_id: int,
    request: Request,
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    judge = db.get(Judge, judge_id)
    if not judge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到評審")
    db.delete(judge)
    db.commit()
    return {"ok": True}


# ---------- Photos ----------


@router.get("/photos")
def photos_page(
    request: Request,
    response: Response,
    group: str = "staff",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    csrf_token = ensure_csrf_cookie(request, response)
    groups = db.query(Group).order_by(Group.id).all()
    current_group = db.query(Group).filter_by(code=group).first()
    photos = []
    if current_group:
        photos = (
            db.query(Photo)
            .filter_by(group_id=current_group.id)
            .order_by(Photo.code)
            .all()
        )
    tmpl_response = templates.TemplateResponse(
        request,
        "admin/photos.html",
        {
            "groups": groups,
            "current_group": group,
            "photos": photos,
            "csrf_token": csrf_token,
            "admin": admin,
        },
    )
    tmpl_response.headers.raw.extend(response.raw_headers)
    return tmpl_response


@router.post("/photos")
async def upload_photo(
    request: Request,
    group: str = Form(...),
    code: str = Form(...),
    title: str = Form(""),
    caption: str = Form(""),
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    group_obj = db.query(Group).filter_by(code=group).first()
    if not group_obj:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="找不到指定組別")
    code = code.strip()
    if db.query(Photo).filter_by(group_id=group_obj.id, code=code).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"組內編號 {code} 已存在")

    stored_name = save_photo_upload(file)
    photo = Photo(
        group_id=group_obj.id,
        code=code,
        image_path=stored_name,
        title=title.strip() or None,
        caption=caption.strip() or None,
    )
    db.add(photo)
    db.commit()
    return RedirectResponse(url=f"/admin/photos?group={group}", status_code=303)


@router.post("/photos/{photo_id}/details")
async def update_photo_details(
    photo_id: int,
    request: Request,
    title: str = Form(""),
    caption: str = Form(""),
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到照片")
    photo.title = title.strip() or None
    photo.caption = caption.strip() or None
    db.commit()
    return RedirectResponse(url=f"/admin/photos?group={photo.group.code}", status_code=303)


@router.delete("/photos/{photo_id}")
async def delete_photo(
    photo_id: int,
    request: Request,
    admin: AdminUser = Depends(require_admin_write),
    db: Session = Depends(get_db),
):
    await verify_csrf(request)
    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到照片")
    stored_name = photo.image_path
    db.delete(photo)
    db.commit()
    delete_photo_file(stored_name)
    return {"ok": True}


# ---------- Results ----------


def _compute_results(db: Session, group_code: str):
    group_obj = db.query(Group).filter_by(code=group_code).first()
    if not group_obj:
        return [], []
    criteria = db.query(Criteria).order_by(Criteria.sort_order, Criteria.id).all()
    judges = db.query(Judge).order_by(Judge.id).all()
    photos = db.query(Photo).filter_by(group_id=group_obj.id).order_by(Photo.code).all()

    rows = []
    for photo in photos:
        scores = db.query(Score).filter_by(photo_id=photo.id).all()
        judged_by = {s.judge_id for s in scores}
        avg = None
        high_score_count = 0
        max_single_score = None
        if scores:
            avg = round(sum(s.weighted_total for s in scores) / len(scores), 2)
            high_score_count = sum(1 for s in scores if s.weighted_total >= HIGH_SCORE_THRESHOLD)
            max_single_score = max(s.weighted_total for s in scores)
        rows.append(
            {
                "photo": photo,
                "average": avg,
                "judged_count": len(scores),
                "total_judges": len(judges),
                "judged_by": judged_by,
                "high_score_count": high_score_count,
                "max_single_score": max_single_score,
            }
        )

    scored_rows = [r for r in rows if r["average"] is not None]
    unscored_rows = [r for r in rows if r["average"] is None]
    # Tie-break cascade: weighted average, then count of judges who gave a
    # "top mark" (>= HIGH_SCORE_THRESHOLD), then the single highest score any
    # judge gave. Only rows where all three match are truly tied.
    scored_rows.sort(key=lambda r: (r["average"], r["high_score_count"], r["max_single_score"]), reverse=True)

    rank = 0
    prev_key = None
    for i, row in enumerate(scored_rows, start=1):
        key = (row["average"], row["high_score_count"], row["max_single_score"])
        if key != prev_key:
            rank = i
            prev_key = key
        row["rank"] = rank

    for row in unscored_rows:
        row["rank"] = None

    return scored_rows + unscored_rows, judges


@router.get("/results")
def results_page(
    request: Request,
    response: Response,
    group: str = "staff",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    csrf_token = ensure_csrf_cookie(request, response)
    groups = db.query(Group).order_by(Group.id).all()
    rows, judges = _compute_results(db, group)
    tmpl_response = templates.TemplateResponse(
        request,
        "admin/results.html",
        {
            "groups": groups,
            "current_group": group,
            "rows": rows,
            "judges": judges,
            "csrf_token": csrf_token,
            "admin": admin,
            "high_score_threshold": HIGH_SCORE_THRESHOLD,
        },
    )
    tmpl_response.headers.raw.extend(response.raw_headers)
    return tmpl_response


@router.get("/results/export.csv")
def export_csv(
    group: str = "staff",
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows, judges = _compute_results(db, group)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = ["排名", "編號", "加權平均分", "已評分評審數", "總評審數", f"≥{HIGH_SCORE_THRESHOLD}分評審人數(破同分用)", "單一評審最高分(破同分用)"]
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            [
                row["rank"] if row["rank"] is not None else "尚未評分",
                row["photo"].code,
                row["average"] if row["average"] is not None else "",
                row["judged_count"],
                row["total_judges"],
                row["high_score_count"] if row["average"] is not None else "",
                row["max_single_score"] if row["average"] is not None else "",
            ]
        )
    buffer.seek(0)
    filename = f"results_{group}.csv"
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- Backup ----------


@router.get("/backup.db")
def download_backup(admin: AdminUser = Depends(require_admin_write)):
    if not DATABASE_URL.startswith("sqlite"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非 SQLite 資料庫,請使用資料庫廠商提供的備份工具")
    db_path = Path(DATABASE_URL.replace("sqlite:///", "", 1))
    if not db_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到資料庫檔案")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp_path = Path(tmp.name)
    shutil.copyfile(db_path, tmp_path)
    return FileResponse(tmp_path, filename="photo-contest-backup.db", background=None)
