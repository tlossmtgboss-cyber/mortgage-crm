"""
Recruiting platform landing page routes.

router       — authenticated CRUD (create, edit, publish, preview)
public_router — serve rendered HTML + track views
"""
import logging
import os
import json
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recruit-platform/landing-pages")
public_router = APIRouter(prefix="/api/v1/recruit-platform")

# ── Lazy deps ──────────────────────────────────────────────────────────────────
def _get_db():
    from database import get_db
    return next(get_db())

def _get_cu():
    from auth.dependencies import get_current_user
    return get_current_user

# ── Template loading ───────────────────────────────────────────────────────────
_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'templates', 'recruit_landing_page.html')
_TEMPLATE_CACHE: Optional[str] = None

def _load_template() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        try:
            with open(_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                _TEMPLATE_CACHE = f.read()
        except FileNotFoundError:
            logger.error("Landing page template not found at %s", _TEMPLATE_PATH)
            raise HTTPException(status_code=500, detail="Template not configured")
    return _TEMPLATE_CACHE

def _render_template(config: dict, org_slug: str, page_slug: str) -> str:
    html = _load_template()
    api_base = os.environ.get('API_BASE_URL', 'https://api.perenniaai.com')
    subs = {
        '{{PAGE_TITLE}}': config.get('page_title', 'Careers — Apply Now'),
        '{{PRIMARY_COLOR}}': config.get('primary_color', '#6AAA26'),
        '{{PRIMARY_COLOR_DARK}}': config.get('primary_color_dark', '#578F1E'),
        '{{PRIMARY_COLOR_PALE}}': config.get('primary_color_pale', '#EFF7E1'),
        '{{LOCATION_DISPLAY}}': config.get('location_display', ''),
        '{{HERO_HEADLINE}}': config.get('hero_headline', 'Join Our Team'),
        '{{HERO_SUBHEADLINE}}': config.get('hero_subheadline', ''),
        '{{SIGNING_BONUS}}': config.get('signing_bonus', '$2,500'),
        '{{SIGNING_BONUS_MONTH}}': config.get('signing_bonus_month', 'this month'),
        '{{SIGNING_BONUS_DEADLINE}}': config.get('signing_bonus_deadline', 'this month'),
        '{{YEAR1_RANGE}}': config.get('year1_range', '$65–90K'),
        '{{YEAR2_TOP}}': config.get('year2_top', '$120,000+'),
        '{{SENIOR_LO}}': config.get('senior_lo', '$180,000+'),
        '{{TEAM_LEAD}}': config.get('team_lead', '$250,000+'),
        '{{STAT_1_NUM}}': config.get('stat_1_num', '2,400+'),
        '{{STAT_1_LABEL}}': config.get('stat_1_label', 'Loans closed last year'),
        '{{STAT_2_NUM}}': config.get('stat_2_num', '94%'),
        '{{STAT_2_LABEL}}': config.get('stat_2_label', 'Employees promoted within 18 months'),
        '{{STAT_3_NUM}}': config.get('stat_3_num', '4.97 ★'),
        '{{STAT_3_LABEL}}': config.get('stat_3_label', 'Team borrower rating'),
        '{{STAT_4_NUM}}': config.get('stat_4_num', '8 Weeks'),
        '{{STAT_4_LABEL}}': config.get('stat_4_label', 'Fully paid training program'),
        '{{MANAGER_INITIALS}}': config.get('manager_initials', ''),
        '{{MANAGER_NAME}}': config.get('manager_name', ''),
        '{{MANAGER_TITLE}}': config.get('manager_title', ''),
        '{{MANAGER_NMLS}}': config.get('manager_nmls', ''),
        '{{CONTACT_PHONE_DISPLAY}}': config.get('contact_phone_display', ''),
        '{{CONTACT_PHONE_TEL}}': config.get('contact_phone_tel', ''),
        '{{COMPANY_NAME}}': config.get('company_name', ''),
        '{{BRANCH_ADDRESS}}': config.get('branch_address', ''),
        '{{BRANCH_NMLS}}': config.get('branch_nmls', ''),
        '{{API_BASE_URL}}': api_base,
        '{{ORG_SLUG}}': org_slug,
        '{{PAGE_SLUG}}': page_slug,
        '{{BASE_HREF}}': '/',
    }
    for placeholder, value in subs.items():
        html = html.replace(placeholder, str(value))
    return html

# ── Pydantic models ────────────────────────────────────────────────────────────
class LandingPageCreate(BaseModel):
    title: str
    slug: str
    config: dict = {}

class LandingPageUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    config: Optional[dict] = None

class ScheduleRequest(BaseModel):
    candidate_id: int
    selected_time: str
    selected_day: str

# ── Auth endpoints (CRUD) ──────────────────────────────────────────────────────

@router.get("/")
async def list_landing_pages(
    db=Depends(_get_db),
    current_user: Any = Depends(_get_cu),
):
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT id, title, slug, status, view_count, submission_count, created_at, updated_at
        FROM recruit_landing_pages
        ORDER BY created_at DESC
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/", status_code=201)
async def create_landing_page(
    body: LandingPageCreate,
    db=Depends(_get_db),
    current_user: Any = Depends(_get_cu),
):
    from sqlalchemy import text
    existing = db.execute(text("SELECT id FROM recruit_landing_pages WHERE slug = :s"), {"s": body.slug}).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already in use")
    row = db.execute(text("""
        INSERT INTO recruit_landing_pages (organization_id, title, slug, config, created_by)
        VALUES (:org, :title, :slug, :cfg::jsonb, :uid)
        RETURNING id, title, slug, status, config, created_at
    """), {
        "org": current_user.organization_id,
        "title": body.title,
        "slug": body.slug,
        "cfg": json.dumps(body.config),
        "uid": current_user.id,
    }).fetchone()
    db.commit()
    return dict(row._mapping)


@router.get("/{page_id}")
async def get_landing_page(
    page_id: int,
    db=Depends(_get_db),
    current_user: Any = Depends(_get_cu),
):
    from sqlalchemy import text
    row = db.execute(text("SELECT * FROM recruit_landing_pages WHERE id = :id"), {"id": page_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Landing page not found")
    return dict(row._mapping)


@router.patch("/{page_id}")
async def update_landing_page(
    page_id: int,
    body: LandingPageUpdate,
    db=Depends(_get_db),
    current_user: Any = Depends(_get_cu),
):
    from sqlalchemy import text
    if not db.execute(text("SELECT id FROM recruit_landing_pages WHERE id = :id"), {"id": page_id}).fetchone():
        raise HTTPException(status_code=404, detail="Landing page not found")
    updates, params = [], {"id": page_id}
    if body.title is not None:
        updates.append("title = :title"); params["title"] = body.title
    if body.slug is not None:
        updates.append("slug = :slug"); params["slug"] = body.slug
    if body.config is not None:
        updates.append("config = :cfg::jsonb"); params["cfg"] = json.dumps(body.config)
    if updates:
        updates.append("updated_at = NOW()")
        db.execute(text(f"UPDATE recruit_landing_pages SET {', '.join(updates)} WHERE id = :id"), params)
        db.commit()
    row = db.execute(text("SELECT * FROM recruit_landing_pages WHERE id = :id"), {"id": page_id}).fetchone()
    return dict(row._mapping)


@router.post("/{page_id}/publish")
async def publish_page(page_id: int, db=Depends(_get_db), current_user: Any = Depends(_get_cu)):
    from sqlalchemy import text
    db.execute(text("UPDATE recruit_landing_pages SET status='published', updated_at=NOW() WHERE id=:id"), {"id": page_id})
    db.commit()
    return {"status": "published"}


@router.post("/{page_id}/unpublish")
async def unpublish_page(page_id: int, db=Depends(_get_db), current_user: Any = Depends(_get_cu)):
    from sqlalchemy import text
    db.execute(text("UPDATE recruit_landing_pages SET status='draft', updated_at=NOW() WHERE id=:id"), {"id": page_id})
    db.commit()
    return {"status": "draft"}


@router.delete("/{page_id}", status_code=204)
async def delete_landing_page(page_id: int, db=Depends(_get_db), current_user: Any = Depends(_get_cu)):
    from sqlalchemy import text
    db.execute(text("DELETE FROM recruit_landing_pages WHERE id=:id"), {"id": page_id})
    db.commit()


@router.get("/{page_id}/preview", response_class=HTMLResponse)
async def preview_landing_page(page_id: int, db=Depends(_get_db), current_user: Any = Depends(_get_cu)):
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT lp.*, o.slug as org_slug
        FROM recruit_landing_pages lp
        JOIN organizations o ON o.id = lp.organization_id
        WHERE lp.id = :id
    """), {"id": page_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Landing page not found")
    data = dict(row._mapping)
    return HTMLResponse(_render_template(data.get('config') or {}, data['org_slug'], data['slug']))


# ── Public endpoints ───────────────────────────────────────────────────────────

@public_router.get("/p/{slug}", response_class=HTMLResponse)
async def serve_landing_page(slug: str):
    from database import get_db
    from sqlalchemy import text
    db = next(get_db())
    try:
        row = db.execute(text("""
            SELECT lp.*, o.slug as org_slug
            FROM recruit_landing_pages lp
            JOIN organizations o ON o.id = lp.organization_id
            WHERE lp.slug = :slug AND lp.status = 'published'
        """), {"slug": slug}).fetchone()
        if not row:
            return HTMLResponse("<h1>Page not found</h1>", status_code=404)
        data = dict(row._mapping)
        db.execute(text("UPDATE recruit_landing_pages SET view_count = view_count + 1 WHERE slug = :s"), {"s": slug})
        db.commit()
        return HTMLResponse(_render_template(data.get('config') or {}, data['org_slug'], data['slug']))
    finally:
        db.close()


@public_router.post("/p/{slug}/view", status_code=204)
async def track_view(slug: str):
    return Response(status_code=204)


@public_router.post("/public/apply/{org_slug}/schedule")
async def schedule_interview(org_slug: str, body: ScheduleRequest):
    from database import get_db
    from sqlalchemy import text
    db = next(get_db())
    try:
        db.execute(text("""
            UPDATE mm_candidates
            SET talent_profile = COALESCE(talent_profile, '{}')::jsonb
                || :update::jsonb
            WHERE id = :id
        """), {
            "id": body.candidate_id,
            "update": json.dumps({"interview_slot": f"{body.selected_time} on {body.selected_day}"}),
        })
        db.commit()
    except Exception:
        pass
    finally:
        db.close()
    return {"ok": True}
