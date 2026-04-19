"""Re-encrypt PII from Fernet (v1) to AES-256-GCM (v2). Online-safe, idempotent."""
import logging
from sqlalchemy import text
from database import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BATCH = 500


def run():
    from services.smart_docs.pii_encryption_service import get_pii_encryption_service
    svc = get_pii_encryption_service()

    if not hasattr(svc, 'needs_reencryption'):
        logger.info("PII service does not support versioned encryption; nothing to do")
        return

    db = SessionLocal()
    try:
        last_id = 0
        total = 0
        while True:
            rows = db.execute(text(
                "SELECT id, ssn_encrypted, account_number_encrypted "
                "FROM smart_documents WHERE id > :last_id ORDER BY id LIMIT :lim"
            ), {"last_id": last_id, "lim": BATCH}).fetchall()
            if not rows:
                break
            for row in rows:
                last_id = row[0]
                updates = {}
                for col_idx, col_name in [(1, "ssn_encrypted"), (2, "account_number_encrypted")]:
                    val = row[col_idx]
                    if val and svc.needs_reencryption(val):
                        try:
                            updates[col_name] = svc.encrypt(svc.decrypt(val))
                        except Exception as e:
                            logger.error("fail smart_documents.%s id=%s: %s", col_name, row[0], e)
                if updates:
                    set_clause = ", ".join(f"{c} = :{c}" for c in updates)
                    updates["doc_id"] = row[0]
                    db.execute(text(
                        f"UPDATE smart_documents SET {set_clause} WHERE id = :doc_id"
                    ), updates)
                    total += 1
            db.commit()
            logger.info("smart_documents: migrated=%s last_id=%s", total, last_id)
    finally:
        db.close()
    logger.info("Re-encryption complete: %s rows updated", total)


if __name__ == "__main__":
    run()
