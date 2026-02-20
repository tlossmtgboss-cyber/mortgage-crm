"""
Webhook Event Catalog Seed Data
Enterprise Readiness - Domain 11, Check 11.7

Populates the webhook_event_catalog table with available webhook events,
their schemas, and example payloads for API documentation.
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database.models import WebhookEventCatalog
import logging

logger = logging.getLogger(__name__)


def seed_webhook_events(db: Session):
    """Populate webhook event catalog with available events."""

    events = [
        # =====================================================================
        # LEAD EVENTS
        # =====================================================================
        {
            "event_id": "lead.created",
            "name": "Lead Created",
            "description": "Triggered when a new lead is created in the system",
            "category": "leads",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "lead.created"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                            "email": {"type": "string", "format": "email"},
                            "phone": {"type": "string"},
                            "source": {"type": "string"},
                            "stage": {"type": "string"},
                            "created_at": {"type": "string", "format": "date-time"}
                        },
                        "required": ["id", "name"]
                    }
                },
                "required": ["event", "timestamp", "data"]
            },
            "example_payload": {
                "event": "lead.created",
                "timestamp": "2026-02-20T15:30:00Z",
                "data": {
                    "id": 12345,
                    "name": "John Doe",
                    "email": "john.doe@example.com",
                    "phone": "+1-555-0123",
                    "source": "website",
                    "stage": "New",
                    "created_at": "2026-02-20T15:30:00Z"
                }
            }
        },
        {
            "event_id": "lead.updated",
            "name": "Lead Updated",
            "description": "Triggered when lead information is updated",
            "category": "leads",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "lead.updated"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "changes": {"type": "object"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "lead.updated",
                "timestamp": "2026-02-20T15:35:00Z",
                "data": {
                    "id": 12345,
                    "changes": {
                        "stage": {"old": "New", "new": "Contacted"}
                    }
                }
            }
        },
        {
            "event_id": "lead.converted",
            "name": "Lead Converted",
            "description": "Triggered when a lead is converted to a loan",
            "category": "leads",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "lead.converted"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer"},
                            "loan_id": {"type": "integer"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "lead.converted",
                "timestamp": "2026-02-20T16:00:00Z",
                "data": {
                    "lead_id": 12345,
                    "loan_id": 67890
                }
            }
        },

        # =====================================================================
        # LOAN EVENTS
        # =====================================================================
        {
            "event_id": "loan.created",
            "name": "Loan Created",
            "description": "Triggered when a new loan is created",
            "category": "loans",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "loan.created"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "loan_number": {"type": "string"},
                            "borrower_name": {"type": "string"},
                            "loan_amount": {"type": "number"},
                            "loan_type": {"type": "string"},
                            "stage": {"type": "string"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "loan.created",
                "timestamp": "2026-02-20T16:00:00Z",
                "data": {
                    "id": 67890,
                    "loan_number": "LN-2026-0001",
                    "borrower_name": "John Doe",
                    "loan_amount": 350000.00,
                    "loan_type": "Conventional",
                    "stage": "Application"
                }
            }
        },
        {
            "event_id": "loan.stage_changed",
            "name": "Loan Stage Changed",
            "description": "Triggered when a loan moves to a different stage",
            "category": "loans",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "loan.stage_changed"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "loan_number": {"type": "string"},
                            "old_stage": {"type": "string"},
                            "new_stage": {"type": "string"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "loan.stage_changed",
                "timestamp": "2026-02-20T17:00:00Z",
                "data": {
                    "id": 67890,
                    "loan_number": "LN-2026-0001",
                    "old_stage": "Application",
                    "new_stage": "Processing"
                }
            }
        },
        {
            "event_id": "loan.funded",
            "name": "Loan Funded",
            "description": "Triggered when a loan is successfully funded",
            "category": "loans",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "loan.funded"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "loan_number": {"type": "string"},
                            "funded_amount": {"type": "number"},
                            "funded_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "loan.funded",
                "timestamp": "2026-03-15T10:00:00Z",
                "data": {
                    "id": 67890,
                    "loan_number": "LN-2026-0001",
                    "funded_amount": 350000.00,
                    "funded_at": "2026-03-15T10:00:00Z"
                }
            }
        },

        # =====================================================================
        # DOCUMENT EVENTS
        # =====================================================================
        {
            "event_id": "document.uploaded",
            "name": "Document Uploaded",
            "description": "Triggered when a document is uploaded to a loan",
            "category": "documents",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "document.uploaded"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "loan_id": {"type": "integer"},
                            "document_type": {"type": "string"},
                            "file_name": {"type": "string"},
                            "uploaded_by": {"type": "string"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "document.uploaded",
                "timestamp": "2026-02-21T09:00:00Z",
                "data": {
                    "id": 1001,
                    "loan_id": 67890,
                    "document_type": "paystub",
                    "file_name": "paystub_jan_2026.pdf",
                    "uploaded_by": "borrower"
                }
            }
        },
        {
            "event_id": "document.approved",
            "name": "Document Approved",
            "description": "Triggered when a document is reviewed and approved",
            "category": "documents",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "document.approved"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "loan_id": {"type": "integer"},
                            "document_type": {"type": "string"},
                            "approved_by": {"type": "string"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "document.approved",
                "timestamp": "2026-02-21T10:00:00Z",
                "data": {
                    "id": 1001,
                    "loan_id": 67890,
                    "document_type": "paystub",
                    "approved_by": "processor@example.com"
                }
            }
        },

        # =====================================================================
        # TASK EVENTS
        # =====================================================================
        {
            "event_id": "task.created",
            "name": "Task Created",
            "description": "Triggered when a new task is created",
            "category": "tasks",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "task.created"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "title": {"type": "string"},
                            "assigned_to": {"type": "string"},
                            "due_date": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "task.created",
                "timestamp": "2026-02-20T15:30:00Z",
                "data": {
                    "id": 5001,
                    "title": "Order appraisal",
                    "assigned_to": "processor@example.com",
                    "due_date": "2026-02-22T17:00:00Z"
                }
            }
        },
        {
            "event_id": "task.completed",
            "name": "Task Completed",
            "description": "Triggered when a task is marked as completed",
            "category": "tasks",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "task.completed"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "title": {"type": "string"},
                            "completed_by": {"type": "string"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "task.completed",
                "timestamp": "2026-02-21T14:00:00Z",
                "data": {
                    "id": 5001,
                    "title": "Order appraisal",
                    "completed_by": "processor@example.com"
                }
            }
        },

        # =====================================================================
        # APPLICATION EVENTS
        # =====================================================================
        {
            "event_id": "application.submitted",
            "name": "Application Submitted",
            "description": "Triggered when a borrower submits a loan application",
            "category": "applications",
            "payload_schema": {
                "type": "object",
                "properties": {
                    "event": {"type": "string", "const": "application.submitted"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "borrower_name": {"type": "string"},
                            "loan_amount": {"type": "number"},
                            "property_address": {"type": "string"}
                        }
                    }
                }
            },
            "example_payload": {
                "event": "application.submitted",
                "timestamp": "2026-02-20T16:00:00Z",
                "data": {
                    "id": 3001,
                    "borrower_name": "Jane Smith",
                    "loan_amount": 425000.00,
                    "property_address": "123 Main St, Austin, TX 78701"
                }
            }
        },
    ]

    # Insert or update events
    for event_data in events:
        existing = db.query(WebhookEventCatalog).filter(
            WebhookEventCatalog.event_id == event_data["event_id"]
        ).first()

        if existing:
            # Update existing event
            for key, value in event_data.items():
                setattr(existing, key, value)
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Create new event
            event = WebhookEventCatalog(**event_data)
            db.add(event)

    try:
        db.commit()
        logger.info(f"Successfully seeded {len(events)} webhook events")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding webhook events: {str(e)}")
        raise


if __name__ == "__main__":
    # Standalone execution for seeding
    from database import get_db

    db = next(get_db())
    try:
        seed_webhook_events(db)
        print("Webhook events seeded successfully")
    finally:
        db.close()
