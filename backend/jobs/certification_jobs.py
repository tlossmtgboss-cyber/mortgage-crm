"""
Background Jobs for Access Certification System
Run quarterly to create certifications and daily for reminders
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import text, and_
import sys
import os
import json
import logging

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal

logger = logging.getLogger(__name__)

def get_user_permissions_dict(user_id: int, db):
    """Get all permissions for a user as a dictionary"""
    query = text("""
        SELECT up.permission_key, up.granted, up.is_temporary, up.granted_until,
               pt.description
        FROM user_permissions up
        LEFT JOIN permission_templates pt ON pt.name = (
            SELECT name FROM permission_templates
            WHERE permissions ? up.permission_key
            LIMIT 1
        )
        WHERE up.user_id = :user_id AND up.granted = TRUE
    """)

    result = db.execute(query, {"user_id": user_id})
    permissions = {}

    for row in result:
        permissions[row.permission_key] = {
            "granted": row.granted,
            "is_temporary": row.is_temporary,
            "granted_until": row.granted_until.isoformat() if row.granted_until else None,
            "description": row.description
        }

    return permissions

def create_quarterly_certifications():
    """
    Run quarterly (or on-demand) to create certification records for all active employees
    Creates certifications due 90 days from creation
    """
    db = SessionLocal()
    try:
        # Get current quarter
        now = datetime.now(timezone.utc)
        quarter = f"Q{(now.month-1)//3 + 1}-{now.year}"

        logger.info(f"📋 Creating access certifications for {quarter}")

        # Get all active employees (excluding temp/inactive accounts)
        query = text("""
            SELECT id, email, full_name, role
            FROM users
            WHERE account_status = 'active'
            AND role IN ('sales', 'operations', 'manager', 'management', 'loan_officer', 'admin')
        """)

        active_employees = db.execute(query).fetchall()
        due_date = (now + timedelta(days=90)).date()

        created_count = 0
        skipped_count = 0

        for employee in active_employees:
            # Check if certification already exists for this period
            existing_query = text("""
                SELECT COUNT(*) as count
                FROM access_certifications
                WHERE employee_id = :employee_id
                AND certification_period = :period
            """)

            existing = db.execute(existing_query, {
                "employee_id": employee.id,
                "period": quarter
            }).fetchone()

            if existing.count > 0:
                skipped_count += 1
                continue

            # Get current permissions snapshot
            permissions = get_user_permissions_dict(employee.id, db)

            # Create certification record
            insert_query = text("""
                INSERT INTO access_certifications
                (employee_id, certification_period, due_date, permissions_snapshot, created_at)
                VALUES (:employee_id, :period, :due_date, CAST(:permissions AS jsonb), CURRENT_TIMESTAMP)
            """)

            db.execute(insert_query, {
                "employee_id": employee.id,
                "period": quarter,
                "due_date": due_date,
                "permissions": json.dumps(permissions)  # Convert to JSON string for CAST
            })

            created_count += 1

        db.commit()
        logger.info(f"✅ Created {created_count} certifications for {quarter} (skipped {skipped_count} existing)")

        return {
            "success": True,
            "created": created_count,
            "skipped": skipped_count,
            "quarter": quarter
        }

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creating certifications: {e}")
        return {"success": False, "error": "Internal server error"}
    finally:
        db.close()

def send_certification_reminders():
    """
    Run daily to send reminder notifications/emails
    - 30 days before due date
    - 7 days before due date
    - On due date (becomes overdue)
    - Daily when overdue
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today = now.date()

        logger.info(f"📧 Checking certification reminders for {today}")

        # 30-day reminders
        due_in_30 = today + timedelta(days=30)
        certs_30d_query = text("""
            SELECT ac.id, ac.employee_id, ac.due_date, ac.certification_period,
                   u.full_name
            FROM access_certifications ac
            JOIN users u ON ac.employee_id = u.id
            WHERE ac.status = 'pending'
            AND ac.due_date = :due_date
            AND ac.reminder_sent_30d = FALSE
        """)

        certs_30d = db.execute(certs_30d_query, {"due_date": due_in_30}).fetchall()

        for cert in certs_30d:
            send_certification_reminder(cert, "30_days", db)
            # Mark reminder as sent
            db.execute(text("""
                UPDATE access_certifications
                SET reminder_sent_30d = TRUE
                WHERE id = :cert_id
            """), {"cert_id": cert.id})

        logger.info(f"   📬 Sent {len(certs_30d)} 30-day reminders")

        # 7-day reminders
        due_in_7 = today + timedelta(days=7)
        certs_7d_query = text("""
            SELECT ac.id, ac.employee_id, ac.due_date, ac.certification_period,
                   u.full_name
            FROM access_certifications ac
            JOIN users u ON ac.employee_id = u.id
            WHERE ac.status = 'pending'
            AND ac.due_date = :due_date
            AND ac.reminder_sent_7d = FALSE
        """)

        certs_7d = db.execute(certs_7d_query, {"due_date": due_in_7}).fetchall()

        for cert in certs_7d:
            send_certification_reminder(cert, "7_days", db)
            db.execute(text("""
                UPDATE access_certifications
                SET reminder_sent_7d = TRUE
                WHERE id = :cert_id
            """), {"cert_id": cert.id})

        logger.info(f"   📬 Sent {len(certs_7d)} 7-day reminders")

        # Overdue certifications
        overdue_query = text("""
            SELECT ac.id, ac.employee_id, ac.due_date, ac.certification_period,
                   u.full_name
            FROM access_certifications ac
            JOIN users u ON ac.employee_id = u.id
            WHERE ac.status = 'pending'
            AND ac.due_date < :today
        """)

        overdue_certs = db.execute(overdue_query, {"today": today}).fetchall()

        for cert in overdue_certs:
            # Update status to overdue
            db.execute(text("""
                UPDATE access_certifications
                SET status = 'overdue'
                WHERE id = :cert_id
            """), {"cert_id": cert.id})

            # Send overdue reminder
            send_certification_reminder(cert, "overdue", db)

        logger.info(f"   ⚠️  Marked {len(overdue_certs)} certifications as overdue")

        db.commit()

        return {
            "success": True,
            "reminders_30d": len(certs_30d),
            "reminders_7d": len(certs_7d),
            "overdue": len(overdue_certs)
        }

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error sending reminders: {e}")
        return {"success": False, "error": "Internal server error"}
    finally:
        db.close()

def send_certification_reminder(cert, reminder_type, db):
    """Create notification for admins about certification (sends to all admins/management)"""
    messages = {
        "30_days": {
            "title": f"Access certification due in 30 days",
            "message": f"Please review and certify {cert.full_name}'s permissions by {cert.due_date}",
            "type": "certification_reminder"
        },
        "7_days": {
            "title": f"⚠️ Access certification due in 7 days",
            "message": f"URGENT: Review {cert.full_name}'s permissions - due {cert.due_date}",
            "type": "certification_reminder"
        },
        "overdue": {
            "title": f"🚨 Access certification OVERDUE",
            "message": f"CRITICAL: {cert.full_name}'s certification is overdue. Immediate action required.",
            "type": "certification_overdue"
        }
    }

    msg = messages[reminder_type]

    # Get all admin/management users to notify
    admin_query = text("""
        SELECT id FROM users
        WHERE role IN ('admin', 'management')
        AND account_status = 'active'
    """)
    admins = db.execute(admin_query).fetchall()

    insert_notification = text("""
        INSERT INTO notifications (user_id, type, title, message, link, created_at)
        VALUES (:user_id, :type, :title, :message, :link, CURRENT_TIMESTAMP)
    """)

    # Send notification to each admin
    for admin in admins:
        db.execute(insert_notification, {
            "user_id": admin.id,
            "type": msg["type"],
            "title": msg["title"],
            "message": msg["message"],
            "link": f"/team-members/{cert.employee_id}?tab=permissions&cert={cert.id}"
        })

    logger.info(f"   📬 Sent {len(admins)} notifications for {cert.full_name}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "create":
            print("Creating quarterly certifications...")
            result = create_quarterly_certifications()
            print(f"Result: {result}")

        elif command == "reminders":
            print("Sending certification reminders...")
            result = send_certification_reminders()
            print(f"Result: {result}")

        else:
            print(f"Unknown command: {command}")
            print("Usage: python certification_jobs.py [create|reminders]")
    else:
        print("Usage: python certification_jobs.py [create|reminders]")
        print("  create    - Create quarterly certifications for all employees")
        print("  reminders - Send reminder notifications for due/overdue certifications")
