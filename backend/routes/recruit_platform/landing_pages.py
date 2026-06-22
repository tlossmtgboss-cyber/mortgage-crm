"""
Recruit Platform — Landing Pages (Website Builder)

Authenticated endpoints (admin, prefix /api/v1/recruit-platform/landing-pages):
  GET    /                           list pages for org
  POST   /                           create page
  GET    /{page_id}                  get single page
  PUT    /{page_id}                  update page
  DELETE /{page_id}                  delete page
  POST   /{page_id}/publish          publish page
  POST   /{page_id}/unpublish        unpublish page
  GET    /{page_id}/preview          render HTML preview

Public endpoints (no auth, prefix /api/v1/recruit-platform):
  GET    /p/{slug}                   serve published landing page HTML
  POST   /public/apply/{org_slug}    receive lead application from form
  POST   /public/schedule/{org_slug} receive calendar slot booking
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "templates" / "recruit_landing_page.html"

API_BASE_URL = os.getenv("API_BASE_URL", "https://api.perenniaai.com")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

landing_pages_router = APIRouter(
    prefix="/api/v1/recruit-platform/landing-pages",
    tags=["recruit-landing-pages"],
)

landing_pages_public_router = APIRouter(
    prefix="/api/v1/recruit-platform",
    tags=["recruit-landing-pages-public"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LandingPageConfig(BaseModel):
    model_config = {"extra": "allow"}

    primary_color: str = "#6AAA26"
    primary_color_dark: str = "#578F1E"
    primary_color_pale: str = "#EFF7E1"
    company_name: str = ""
    company_nmls_id: str = ""
    location_display: str = ""
    hero_headline: str = "Build a six-figure mortgage career from day one."
    hero_headline_plain: str = "Build a six-figure mortgage career from day one."
    signing_bonus: str = "$2,500 signing bonus for July hires"
    signing_bonus_amount: str = "$2,500"
    year1_range: str = "$65–90K"
    year2_top: str = "$120,000+"
    senior_lo: str = "$180,000+"
    team_lead: str = "$250,000+"
    stat_1_num: str = "2,400+"
    stat_1_label: str = "Loans closed last year"
    stat_2_num: str = "94%"
    stat_2_label: str = "Employees promoted within 18 months"
    stat_3_num: str = "4.97 ★"
    stat_3_label: str = "Team borrower rating"
    stat_4_num: str = "8 Weeks"
    stat_4_label: str = "Fully paid training program"
    manager_name: str = ""
    manager_initials: str = ""
    manager_title: str = "Branch Manager"
    manager_nmls: str = ""
    contact_phone_display: str = ""
    contact_phone_tel: str = ""
    branch_name: str = ""
    branch_address: str = ""
    branch_nmls: str = ""


class LandingPageCreate(BaseModel):
    title: str
    slug: str
    config: Optional[LandingPageConfig] = None


class LandingPageUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    config: Optional[LandingPageConfig] = None


class ApplicationSubmission(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    experience: Optional[str] = None
    page_slug: Optional[str] = None


class ScheduleSlot(BaseModel):
    slot: Optional[str] = None
    page_slug: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_tenant_id(org_slug: str, db: Session) -> Optional[int]:
    row = db.execute(
        text("SELECT id FROM organizations WHERE slug = :s LIMIT 1"),
        {"s": org_slug},
    ).fetchone()
    return row[0] if row else None


def _render(config: dict, org_slug: str, page_slug: str) -> str:
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="Landing page template not found")

    with open(TEMPLATE_PATH) as f:
        html = f.read()

    subs = {
        "{{PRIMARY_COLOR}}": config.get("primary_color", "#6AAA26"),
        "{{PRIMARY_COLOR_DARK}}": config.get("primary_color_dark", "#578F1E"),
        "{{PRIMARY_COLOR_PALE}}": config.get("primary_color_pale", "#EFF7E1"),
        "{{COMPANY_NAME}}": config.get("company_name", ""),
        "{{COMPANY_NMLS_ID}}": config.get("company_nmls_id", ""),
        "{{LOCATION_DISPLAY}}": config.get("location_display", ""),
        "{{HERO_HEADLINE}}": config.get("hero_headline", ""),
        "{{HERO_SUBHEADLINE}}": config.get("hero_subheadline", ""),
        "{{HERO_HEADLINE_PLAIN}}": config.get("hero_headline_plain", config.get("hero_headline", "")),
        "{{SIGNING_BONUS}}": config.get("signing_bonus", ""),
        "{{SIGNING_BONUS_AMOUNT}}": config.get("signing_bonus_amount", ""),
        "{{YEAR1_RANGE}}": config.get("year1_range", ""),
        "{{YEAR2_TOP}}": config.get("year2_top", ""),
        "{{SENIOR_LO}}": config.get("senior_lo", ""),
        "{{TEAM_LEAD}}": config.get("team_lead", ""),
        "{{STAT_1_NUM}}": config.get("stat_1_num", ""),
        "{{STAT_1_LABEL}}": config.get("stat_1_label", ""),
        "{{STAT_2_NUM}}": config.get("stat_2_num", ""),
        "{{STAT_2_LABEL}}": config.get("stat_2_label", ""),
        "{{STAT_3_NUM}}": config.get("stat_3_num", ""),
        "{{STAT_3_LABEL}}": config.get("stat_3_label", ""),
        "{{STAT_4_NUM}}": config.get("stat_4_num", ""),
        "{{STAT_4_LABEL}}": config.get("stat_4_label", ""),
        "{{MANAGER_NAME}}": config.get("manager_name", ""),
        "{{MANAGER_INITIALS}}": config.get("manager_initials", ""),
        "{{MANAGER_TITLE}}": config.get("manager_title", "Branch Manager"),
        "{{MANAGER_NMLS}}": config.get("manager_nmls", ""),
        "{{CONTACT_PHONE_DISPLAY}}": config.get("contact_phone_display", ""),
        "{{CONTACT_PHONE_TEL}}": config.get("contact_phone_tel", ""),
        "{{BRANCH_NAME}}": config.get("branch_name", ""),
        "{{BRANCH_ADDRESS}}": config.get("branch_address", ""),
        "{{BRANCH_NMLS}}": config.get("branch_nmls", ""),
        "{{API_BASE_URL}}": API_BASE_URL,
        "{{ORG_SLUG}}": org_slug,
        "{{PAGE_SLUG}}": page_slug,
    }

    for placeholder, value in subs.items():
        html = html.replace(placeholder, value)

    return html


def _page_row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "organization_id": row[1],
        "title": row[2],
        "slug": row[3],
        "status": row[4],
        "config": row[5] or {},
        "view_count": row[6],
        "submission_count": row[7],
        "created_by": row[8],
        "created_at": row[9].isoformat() if row[9] else None,
        "updated_at": row[10].isoformat() if row[10] else None,
    }


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

def _auto_seed_callcenter(db, org_id: int) -> None:
    """Seed the callcenter page for org_id if it doesn't exist yet."""
    import json as _json
    from migrations.add_recruit_landing_pages import _CALLCENTER_CONFIG
    org_row = db.execute(
        text("SELECT slug FROM organizations WHERE id = :oid LIMIT 1"), {"oid": org_id}
    ).fetchone()
    org_slug = org_row[0] if org_row else f"org-{org_id}"
    config = dict(_CALLCENTER_CONFIG)
    config["org_slug"] = org_slug
    db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
    db.execute(text("""
        INSERT INTO recruit_landing_pages
            (organization_id, title, slug, status, config)
        VALUES (:oid, :title, :slug, 'published', CAST(:config AS JSONB))
        ON CONFLICT (organization_id, slug) DO NOTHING
    """), {
        "oid": org_id,
        "title": "Call Center — SC",
        "slug": "callcenter",
        "config": _json.dumps(config),
    })
    db.commit()


@landing_pages_router.get("")
def list_landing_pages(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization")

    db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
    rows = db.execute(
        text("""
            SELECT id, organization_id, title, slug, status, config,
                   view_count, submission_count, created_by, created_at, updated_at
            FROM recruit_landing_pages
            WHERE organization_id = :oid
            ORDER BY updated_at DESC
        """),
        {"oid": org_id},
    ).fetchall()

    # Auto-seed callcenter starter page on first load for this org
    if not rows:
        try:
            _auto_seed_callcenter(db, org_id)
            # Re-set tenant context after commit (SET LOCAL is cleared on commit)
            db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
            rows = db.execute(
                text("""
                    SELECT id, organization_id, title, slug, status, config,
                           view_count, submission_count, created_by, created_at, updated_at
                    FROM recruit_landing_pages
                    WHERE organization_id = :oid
                    ORDER BY updated_at DESC
                """),
                {"oid": org_id},
            ).fetchall()
        except Exception as e:
            logger.warning(f"Auto-seed callcenter failed for org {org_id}: {e}")
            db.rollback()

    return [_page_row_to_dict(r) for r in rows]


@landing_pages_router.post("", status_code=201)
def create_landing_page(
    body: LandingPageCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization")

    config = body.config.model_dump() if body.config else {}

    try:
        db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
        row = db.execute(
            text("""
                INSERT INTO recruit_landing_pages
                    (organization_id, title, slug, status, config, created_by)
                VALUES (:oid, :title, :slug, 'draft', :config::jsonb, :uid)
                RETURNING id, organization_id, title, slug, status, config,
                          view_count, submission_count, created_by, created_at, updated_at
            """),
            {
                "oid": org_id,
                "title": body.title,
                "slug": body.slug.lower().strip(),
                "config": __import__("json").dumps(config),
                "uid": getattr(current_user, "id", None),
            },
        ).fetchone()
        db.commit()
    except Exception as e:
        db.rollback()
        if "uq_recruit_landing_pages_org_slug" in str(e):
            raise HTTPException(status_code=409, detail="Slug already exists")
        raise HTTPException(status_code=500, detail=str(e))

    return _page_row_to_dict(row)


@landing_pages_router.get("/{page_id}")
def get_landing_page(
    page_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    row = db.execute(
        text("""
            SELECT id, organization_id, title, slug, status, config,
                   view_count, submission_count, created_by, created_at, updated_at
            FROM recruit_landing_pages
            WHERE id = :pid AND organization_id = :oid
        """),
        {"pid": page_id, "oid": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Page not found")

    return _page_row_to_dict(row)


@landing_pages_router.put("/{page_id}")
def update_landing_page(
    page_id: int,
    body: LandingPageUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import json
    org_id = getattr(current_user, "organization_id", None)

    db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
    existing = db.execute(
        text("SELECT id, config FROM recruit_landing_pages WHERE id = :pid AND organization_id = :oid"),
        {"pid": page_id, "oid": org_id},
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Page not found")

    updates = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.slug is not None:
        updates["slug"] = body.slug.lower().strip()
    if body.config is not None:
        updates["config"] = json.dumps(body.config.model_dump(warnings=False))

    if not updates:
        return {"detail": "no changes"}

    # Build SET clause — use CAST(:config AS JSONB) instead of :config::jsonb
    # because psycopg2 parses ::jsonb as a broken named-parameter token.
    set_parts = []
    for k in updates:
        if k == "config":
            set_parts.append("config = CAST(:config AS JSONB)")
        else:
            set_parts.append(f"{k} = :{k}")
    set_clauses = ", ".join(set_parts) + ", updated_at = NOW()"
    params = {**updates, "pid": page_id, "oid": org_id}

    try:
        row = db.execute(
            text(f"""
                UPDATE recruit_landing_pages SET {set_clauses}
                WHERE id = :pid AND organization_id = :oid
                RETURNING id, organization_id, title, slug, status, config,
                          view_count, submission_count, created_by, created_at, updated_at
            """),
            params,
        ).fetchone()
        db.commit()
    except Exception as e:
        db.rollback()
        if "uq_recruit_landing_pages_org_slug" in str(e):
            raise HTTPException(status_code=409, detail="Slug already exists")
        raise

    return _page_row_to_dict(row)


@landing_pages_router.delete("/{page_id}", status_code=204)
def delete_landing_page(
    page_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
    result = db.execute(
        text("DELETE FROM recruit_landing_pages WHERE id = :pid AND organization_id = :oid"),
        {"pid": page_id, "oid": org_id},
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Page not found")


@landing_pages_router.post("/{page_id}/publish")
def publish_landing_page(
    page_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
    row = db.execute(
        text("""
            UPDATE recruit_landing_pages SET status = 'published', updated_at = NOW()
            WHERE id = :pid AND organization_id = :oid
            RETURNING id, organization_id, title, slug, status, config,
                      view_count, submission_count, created_by, created_at, updated_at
        """),
        {"pid": page_id, "oid": org_id},
    ).fetchone()
    db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found")
    return _page_row_to_dict(row)


@landing_pages_router.post("/{page_id}/unpublish")
def unpublish_landing_page(
    page_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
    row = db.execute(
        text("""
            UPDATE recruit_landing_pages SET status = 'draft', updated_at = NOW()
            WHERE id = :pid AND organization_id = :oid
            RETURNING id, organization_id, title, slug, status, config,
                      view_count, submission_count, created_by, created_at, updated_at
        """),
        {"pid": page_id, "oid": org_id},
    ).fetchone()
    db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found")
    return _page_row_to_dict(row)


@landing_pages_router.get("/{page_id}/preview")
def preview_landing_page(
    page_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = getattr(current_user, "organization_id", None)
    row = db.execute(
        text("""
            SELECT rp.id, rp.slug, rp.config, t.slug
            FROM recruit_landing_pages rp
            JOIN organizations t ON t.id = rp.organization_id
            WHERE rp.id = :pid AND rp.organization_id = :oid
        """),
        {"pid": page_id, "oid": org_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found")

    html = _render(row[2] or {}, row[3], row[1])
    return Response(content=html, media_type="text/html")


@landing_pages_router.post("/seed-callcenter", status_code=201)
def seed_callcenter_page(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from migrations.add_recruit_landing_pages import _CALLCENTER_CONFIG
    import json as _json
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization")

    # Look up org slug for form submission URLs
    org_row = db.execute(
        text("SELECT slug FROM organizations WHERE id = :oid LIMIT 1"), {"oid": org_id}
    ).fetchone()
    org_slug = org_row[0] if org_row else f"org-{org_id}"

    config = dict(_CALLCENTER_CONFIG)
    config["org_slug"] = org_slug

    try:
        db.execute(text(f"SET LOCAL app.current_tenant = '{org_id}'"))
        row = db.execute(text("""
            INSERT INTO recruit_landing_pages
                (organization_id, title, slug, status, config, created_by)
            VALUES (:oid, :title, :slug, 'published', CAST(:config AS JSONB), :uid)
            ON CONFLICT (organization_id, slug)
            DO UPDATE SET
                config = CAST(EXCLUDED.config AS JSONB),
                status = 'published',
                updated_at = NOW()
            RETURNING id, title, slug, status
        """), {
            "oid": org_id,
            "title": "Call Center — SC",
            "slug": "callcenter",
            "config": _json.dumps(config),
            "uid": getattr(current_user, "id", None),
        }).fetchone()
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    return {"seeded": True, "page": {"id": row[0], "title": row[1], "slug": row[2]}}


# ---------------------------------------------------------------------------
# Diagnostic endpoint — returns DB state for debugging
# ---------------------------------------------------------------------------

@landing_pages_router.get("/diag")
def diag_landing_pages(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return raw DB state to diagnose why list returns empty."""
    import os as _os
    org_id = getattr(current_user, "organization_id", None)
    user_id = getattr(current_user, "id", None)
    user_role = getattr(current_user, "role", None)

    # Raw count bypassing org filter
    total_rows = db.execute(text("SELECT COUNT(*) FROM recruit_landing_pages")).scalar()
    # Rows for this user's org
    org_rows = db.execute(
        text("SELECT id, organization_id, slug, status FROM recruit_landing_pages WHERE organization_id = :oid"),
        {"oid": org_id},
    ).fetchall()
    # All org_ids in table
    all_orgs_in_table = db.execute(
        text("SELECT DISTINCT organization_id FROM recruit_landing_pages ORDER BY organization_id")
    ).fetchall()
    # Current app.current_tenant value
    try:
        tenant_val = db.execute(text("SELECT current_setting('app.current_tenant', TRUE)")).scalar()
    except Exception:
        tenant_val = "error"
    # Force RLS status
    try:
        force_rls = db.execute(text(
            "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'recruit_landing_pages'"
        )).scalar()
    except Exception:
        force_rls = "error"

    return {
        "user_id": user_id,
        "user_org_id": org_id,
        "user_role": user_role,
        "total_rows_in_table": total_rows,
        "rows_for_your_org": [dict(id=r[0], org_id=r[1], slug=r[2], status=r[3]) for r in org_rows],
        "all_org_ids_in_table": [r[0] for r in all_orgs_in_table],
        "app_current_tenant": tenant_val,
        "force_row_level_security": force_rls,
    }


# ---------------------------------------------------------------------------
# Admin seed endpoint (no CRM auth — uses X-Admin-Key header)
# ---------------------------------------------------------------------------

@landing_pages_public_router.post("/admin/seed-callcenter", status_code=200)
def admin_seed_callcenter(x_admin_key: str = Header(...)):
    """Seed callcenter page for all orgs. Protected by X-Admin-Key header."""
    import os as _os, json as _json
    from sqlalchemy import create_engine as _ce
    from sqlalchemy import text as _text
    if x_admin_key != _os.environ.get("ADMIN_SEED_KEY", "perennia-seed-2026"):
        raise HTTPException(status_code=403, detail="Forbidden")
    from migrations.add_recruit_landing_pages import _CALLCENTER_CONFIG
    db_url = _os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise HTTPException(status_code=500, detail="No DATABASE_URL")
    eng = _ce(db_url)
    results = []
    try:
        with eng.connect() as c:
            orgs = c.execute(_text("SELECT id, slug FROM organizations WHERE slug IS NOT NULL AND slug != ''")).fetchall()
        for org_id, org_slug in orgs:
            try:
                with eng.begin() as c2:
                    c2.execute(_text(f"SET app.current_tenant = '{org_slug}'"))
                    r = c2.execute(_text("""
                        INSERT INTO recruit_landing_pages
                            (organization_id, title, slug, status, config)
                        VALUES (:oid, :title, :slug, 'published', CAST(:cfg AS jsonb))
                        ON CONFLICT (organization_id, slug)
                        DO UPDATE SET
                            config = CAST(EXCLUDED.config AS jsonb),
                            status = 'published',
                            updated_at = NOW()
                        RETURNING id
                    """), {"oid": org_id, "title": "Call Center — SC",
                           "slug": "callcenter", "cfg": _json.dumps(_CALLCENTER_CONFIG)}).fetchone()
                results.append({"org_id": org_id, "slug": org_slug, "inserted": r is not None})
            except Exception as e:
                results.append({"org_id": org_id, "slug": org_slug, "error": str(e)})
    finally:
        eng.dispose()
    return {"results": results}


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@landing_pages_public_router.get("/careers/{slug}")
@landing_pages_public_router.get("/p/{slug}")
def serve_landing_page(slug: str, db: Session = Depends(get_db)):
    row = db.execute(
        text("""
            SELECT rp.id, rp.slug, rp.config,
                   COALESCE(t.slug, rp.config->>'org_slug', '') AS org_slug
            FROM recruit_landing_pages rp
            LEFT JOIN organizations t ON t.id = rp.organization_id
            WHERE rp.slug = :slug AND rp.status = 'published'
            ORDER BY rp.updated_at DESC
            LIMIT 1
        """),
        {"slug": slug},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Page not found")

    # Increment view count asynchronously
    try:
        db.execute(
            text("UPDATE recruit_landing_pages SET view_count = view_count + 1 WHERE id = :pid"),
            {"pid": row[0]},
        )
        db.commit()
    except Exception:
        db.rollback()

    html = _render(row[2] or {}, row[3], row[1])
    return Response(content=html, media_type="text/html")


@landing_pages_public_router.post("/public/apply/{org_slug}", status_code=201)
def submit_application(
    org_slug: str,
    body: ApplicationSubmission,
    db: Session = Depends(get_db),
):
    tenant_id = _get_tenant_id(org_slug, db)
    if not tenant_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Increment submission count
    if body.page_slug:
        try:
            db.execute(
                text("""
                    UPDATE recruit_landing_pages
                    SET submission_count = submission_count + 1
                    WHERE organization_id = :oid AND slug = :slug
                """),
                {"oid": tenant_id, "slug": body.page_slug},
            )
        except Exception:
            pass

    # Insert applicant record (reuse existing recruit_applicants table if it exists)
    try:
        db.execute(
            text("""
                INSERT INTO recruit_applicants
                    (organization_id, first_name, last_name, email, phone,
                     experience_level, source, stage, created_at)
                VALUES (:oid, :fn, :ln, :email, :phone, :exp, :src, 'new', NOW())
                ON CONFLICT (organization_id, email) DO NOTHING
            """),
            {
                "oid": tenant_id,
                "fn": body.first_name or "",
                "ln": body.last_name or "",
                "email": body.email or "",
                "phone": body.phone or "",
                "exp": body.experience or "",
                "src": f"landing:{body.page_slug or 'unknown'}",
            },
        )
    except Exception as e:
        logger.warning(f"Could not insert applicant from landing page: {e}")

    db.commit()
    return {"status": "received"}


@landing_pages_public_router.post("/public/schedule/{org_slug}", status_code=201)
def submit_schedule(
    org_slug: str,
    body: ScheduleSlot,
    db: Session = Depends(get_db),
):
    tenant_id = _get_tenant_id(org_slug, db)
    if not tenant_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    logger.info(f"Schedule slot submitted for org {org_slug}: {body.slot}")
    return {"status": "received"}
