"""
Diagnostic script: Check scheduler + Outlook calendar integration status
for admin@perenniaai.com.

Usage: cd backend && python scripts/diag_scheduler_outlook.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date, timedelta

def main():
    from db import SessionLocal
    db = SessionLocal()

    print("=" * 70)
    print("SCHEDULER + OUTLOOK DIAGNOSTIC — admin@perenniaai.com")
    print("=" * 70)

    # 1. Find the admin user
    from database.models import User
    admin = db.query(User).filter(User.email == "admin@perenniaai.com").first()
    if not admin:
        # Try case-insensitive
        from sqlalchemy import func
        admin = db.query(User).filter(func.lower(User.email) == "admin@perenniaai.com").first()
    if not admin:
        print("\n[FAIL] User admin@perenniaai.com NOT FOUND in users table")
        # List all users for debugging
        all_users = db.query(User.id, User.email, User.first_name, User.last_name).limit(10).all()
        print("  First 10 users:")
        for u in all_users:
            print(f"    id={u.id}, email={u.email}, name={u.first_name} {u.last_name}")
        db.close()
        return

    print(f"\n[OK] User found: id={admin.id}, email={admin.email}, "
          f"name={getattr(admin, 'first_name', '')} {getattr(admin, 'last_name', '')}, "
          f"org_id={getattr(admin, 'organization_id', 'N/A')}")

    org_id = getattr(admin, 'organization_id', None)

    # 2. Check SchedulerConfig
    print("\n--- SCHEDULER CONFIG ---")
    try:
        from database.models.scheduler import SchedulerConfig
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == admin.id
        ).first()
        if config:
            print(f"[OK] SchedulerConfig found: id={config.id}, active={config.is_active}, tz={config.timezone}")
            wh = config.working_hours
            if wh:
                print(f"  working_hours type: {type(wh).__name__}")
                enabled_days = [k for k, v in wh.items() if isinstance(v, dict) and v.get('enabled')]
                disabled_days = [k for k, v in wh.items() if isinstance(v, dict) and not v.get('enabled')]
                print(f"  Enabled days: {enabled_days}")
                print(f"  Disabled days: {disabled_days}")
                if not enabled_days:
                    print("  [WARN] NO days enabled! Slots will not be generated.")
            else:
                print(f"  [WARN] working_hours is {wh!r} — will fall back to DEFAULT_WORKING_HOURS")
            print(f"  min_notice_hours={getattr(config, 'min_notice_hours', 'N/A')}")
            print(f"  max_advance_days={getattr(config, 'max_advance_days', 'N/A')}")
            print(f"  buffer_before={getattr(config, 'buffer_before_minutes', 'N/A')}min")
            print(f"  buffer_after={getattr(config, 'buffer_after_minutes', 'N/A')}min")
            print(f"  max_meetings_per_day={getattr(config, 'max_meetings_per_day', 'N/A')}")
        else:
            print("[FAIL] No SchedulerConfig for this user — auto-create on demo slug will create one")
    except Exception as e:
        print(f"[ERROR] Checking SchedulerConfig: {e}")

    # 3. Check AppointmentType
    print("\n--- APPOINTMENT TYPES ---")
    try:
        from database.models.scheduler import AppointmentType
        if config:
            types = db.query(AppointmentType).filter(
                AppointmentType.config_id == config.id,
                AppointmentType.is_active == True
            ).all()
        else:
            types = []
        if types:
            for t in types:
                print(f"[OK] Type: id={t.id}, name='{t.type_name}', duration={t.default_duration_minutes}min, public={t.is_public}")
        else:
            print("[WARN] No active appointment types — will be auto-created on demo slug")
    except Exception as e:
        print(f"[ERROR] Checking AppointmentType: {e}")

    # 4. Check BookingLink for demo
    print("\n--- BOOKING LINKS (demo) ---")
    try:
        from database.models.scheduler import BookingLink
        demo_links = db.query(BookingLink).filter(
            BookingLink.slug.like("demo%")
        ).all()
        if demo_links:
            for bl in demo_links:
                print(f"[OK] BookingLink: slug='{bl.slug}', active={bl.is_active}, public={bl.is_public}, "
                      f"user_id={bl.user_id}, org_id={bl.organization_id}")
                print(f"     type_ids={bl.appointment_type_ids}, views={bl.view_count}, bookings={bl.booking_count}")
        else:
            print("[INFO] No demo booking links exist — will be auto-created on first visit")
    except Exception as e:
        print(f"[ERROR] Checking BookingLink: {e}")

    # 5. Check Microsoft OAuth tokens
    print("\n--- MICROSOFT OAUTH ---")

    # Check user_integrations table (older path)
    try:
        from sqlalchemy import text
        rows = db.execute(text(
            "SELECT id, provider, email, expires_at, scopes, "
            "CASE WHEN access_token IS NOT NULL AND access_token != '' THEN 'present' ELSE 'missing' END as has_access, "
            "CASE WHEN refresh_token IS NOT NULL AND refresh_token != '' THEN 'present' ELSE 'missing' END as has_refresh "
            "FROM user_integrations WHERE user_id = :uid"
        ), {"uid": admin.id}).fetchall()
        if rows:
            print(f"  user_integrations rows: {len(rows)}")
            for r in rows:
                expired = "EXPIRED" if r.expires_at and r.expires_at < datetime.utcnow() else "valid"
                print(f"    provider='{r.provider}', email={r.email}, "
                      f"access={r.has_access}, refresh={r.has_refresh}, "
                      f"expires={r.expires_at} ({expired}), scopes={r.scopes}")
        else:
            print("  user_integrations: no rows for this user")
    except Exception as e:
        print(f"  user_integrations check: {e}")

    # Check microsoft_oauth_tokens table (newer path)
    try:
        from database.models.microsoft import MicrosoftOAuthToken
        token = db.query(MicrosoftOAuthToken).filter(
            MicrosoftOAuthToken.user_id == admin.id
        ).first()
        if token:
            expired = "EXPIRED" if token.token_expires_at and token.token_expires_at < datetime.utcnow() else "valid"
            print(f"  microsoft_oauth_tokens: email={token.email_address}, "
                  f"sync={token.sync_enabled}, expires={token.token_expires_at} ({expired}), "
                  f"last_sync={token.last_sync_at}")
            has_access = bool(token.access_token)
            has_refresh = bool(token.refresh_token)
            print(f"    access_token={'present' if has_access else 'MISSING'}, "
                  f"refresh_token={'present' if has_refresh else 'MISSING'}")
        else:
            print("  microsoft_oauth_tokens: no row for this user")
    except Exception as e:
        print(f"  microsoft_oauth_tokens check: {e}")

    # Check MicrosoftAppConfig (org-level)
    try:
        from database.models.microsoft import MicrosoftAppConfig
        app_config = db.query(MicrosoftAppConfig).filter(
            MicrosoftAppConfig.organization_id == org_id
        ).first() if org_id else None
        if not app_config:
            app_config = db.query(MicrosoftAppConfig).first()
        if app_config:
            print(f"  MicrosoftAppConfig: client_id={app_config.client_id[:12]}..., "
                  f"tenant_id={app_config.tenant_id}, org_id={app_config.organization_id}")
        else:
            print("  MicrosoftAppConfig: none found — will use env vars")
            cid = os.getenv("MICROSOFT_CLIENT_ID", "")
            csec = os.getenv("MICROSOFT_CLIENT_SECRET", "")
            print(f"    MICROSOFT_CLIENT_ID={'set' if cid else 'NOT SET'}")
            print(f"    MICROSOFT_CLIENT_SECRET={'set' if csec else 'NOT SET'}")
    except Exception as e:
        print(f"  MicrosoftAppConfig check: {e}")

    # 6. Check CalendarEventMap for this user's appointments
    print("\n--- CALENDAR SYNC STATUS ---")
    try:
        from database.models.calendar_event_map import CalendarEventMap
        from database.models.scheduler import Appointment
        recent_appts = db.query(Appointment).filter(
            Appointment.assigned_user_id == admin.id,
        ).order_by(Appointment.created_at.desc()).limit(5).all()
        if recent_appts:
            print(f"  Recent appointments: {len(recent_appts)}")
            for a in recent_appts:
                cem = db.query(CalendarEventMap).filter(
                    CalendarEventMap.appointment_id == a.id
                ).first()
                sync_info = f"sync={cem.sync_status}, ext_id={cem.external_id[:20]}..." if cem else "NO SYNC"
                print(f"    appt id={a.id}, start={a.scheduled_start}, status={a.status}, {sync_info}")
        else:
            print("  No appointments found for this user")
    except Exception as e:
        print(f"  Calendar sync check: {e}")

    # 7. Test slot generation for tomorrow
    print("\n--- SLOT GENERATION TEST ---")
    try:
        from routes.scheduler._availability import _generate_available_slots
        tomorrow = date.today() + timedelta(days=1)
        # Skip weekends
        while tomorrow.weekday() >= 5:
            tomorrow += timedelta(days=1)

        slots = _generate_available_slots(
            db=db,
            user_ids=[admin.id],
            start_date=tomorrow,
            end_date=tomorrow,
            duration_minutes=30,
            org_id=org_id,
            check_cross_source=False,  # Skip external calendar checks
        )
        print(f"  Slots for {tomorrow} (no cross-source): {len(slots)}")
        if slots:
            print(f"    First: {slots[0].get('start', slots[0].get('start_time'))}")
            print(f"    Last:  {slots[-1].get('start', slots[-1].get('start_time'))}")
        else:
            print("  [WARN] Zero slots generated! Check working_hours config above.")

        # Now with cross-source
        slots_cs = _generate_available_slots(
            db=db,
            user_ids=[admin.id],
            start_date=tomorrow,
            end_date=tomorrow,
            duration_minutes=30,
            org_id=org_id,
            check_cross_source=True,
        )
        print(f"  Slots for {tomorrow} (with cross-source): {len(slots_cs)}")
        if len(slots) > 0 and len(slots_cs) == 0:
            print("  [WARN] Cross-source conflicts blocking ALL slots — calendar integration may be failing closed")
    except Exception as e:
        print(f"  [ERROR] Slot generation: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)
    db.close()


if __name__ == "__main__":
    main()
