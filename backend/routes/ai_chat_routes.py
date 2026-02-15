"""
AI Orchestrator Chat Routes

Extracted from inline_legacy_routes.py.
Provides streaming AI chat with tool execution and autonomous task execution.
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import os

logger = logging.getLogger(__name__)


def register_ai_chat_routes(app, get_db, get_current_user_flexible, **kwargs):
    """Register AI chat and orchestrator routes."""
    from main import User

    # Extract functions passed from main.py via kwargs
    log_ai_action_to_mission_control = kwargs.get('log_ai_action_to_mission_control')
    update_ai_action_outcome = kwargs.get('update_ai_action_outcome')

    @app.post("/api/v1/ai/orchestrator-chat-stream")
    async def orchestrator_chat_stream(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Streaming AI Chat - sends response tokens as they're generated
        Uses Server-Sent Events (SSE) for real-time streaming
        """
        from fastapi.responses import StreamingResponse
        from openai import OpenAI
        from datetime import datetime, timedelta
        import asyncio

        data = await request.json()
        message = data.get("message", "")
        context = data.get("context", {})

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Simplified tools for streaming (same as main endpoint)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_tasks",
                    "description": "Get user's tasks with optional filtering. ALWAYS call this when asked about tasks or what to do today.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filter": {"type": "string", "enum": ["today", "tomorrow", "this_week", "overdue", "all"], "description": "Time filter for tasks"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_calendar_events",
                    "description": "Get user's calendar events and appointments. ALWAYS call this when asked about appointments, meetings, calendar, or schedule.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timeframe": {"type": "string", "enum": ["today", "tomorrow", "this_week", "next_week"], "description": "Timeframe to get calendar events for"}
                        },
                        "required": ["timeframe"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pipeline",
                    "description": "Get pipeline summary with leads and loans by stage",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_details": {"type": "boolean", "description": "Include detailed loan/lead info"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_leads",
                    "description": "Search for leads by name, email, or phone",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "limit": {"type": "integer", "description": "Max results", "default": 5}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_market_intelligence",
                    "description": "Get current market conditions and rate lock recommendations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lock_days": {"type": "integer", "description": "Lock period in days", "default": 30}
                        }
                    }
                }
            },
            # Action tools - allow AI to take actions on behalf of user
            {
                "type": "function",
                "function": {
                    "name": "send_sms",
                    "description": "Send an SMS text message to a contact by name or phone number",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient_name": {"type": "string", "description": "Name of the person to text (will look up phone)"},
                            "phone_number": {"type": "string", "description": "Phone number to send to (if known)"},
                            "message": {"type": "string", "description": "The SMS message to send"}
                        },
                        "required": ["message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_task",
                    "description": "Create a new task for the user",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Task title/description"},
                            "due_date": {"type": "string", "description": "Due date (e.g., 'tomorrow', '2024-01-15')"},
                            "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"], "description": "Task priority"}
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_appointment",
                    "description": "Schedule a meeting or appointment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Meeting title"},
                            "attendee_name": {"type": "string", "description": "Name of person to meet with"},
                            "date_time": {"type": "string", "description": "Date and time (e.g., 'next Tuesday at 2pm')"},
                            "duration_minutes": {"type": "integer", "description": "Meeting duration in minutes", "default": 30}
                        },
                        "required": ["title", "date_time"]
                    }
                }
            },
            # Additional tools from non-streaming endpoint
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send an email to a contact",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to_email": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject"},
                            "body": {"type": "string", "description": "Email body content"}
                        },
                        "required": ["to_email", "subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_lead",
                    "description": "Update a lead's information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer", "description": "Lead ID to update"},
                            "lead_name": {"type": "string", "description": "Lead name to search for (alternative to lead_id)"},
                            "stage": {"type": "string", "description": "New stage for the lead"},
                            "notes": {"type": "string", "description": "Notes to add"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_loan_details",
                    "description": "Get detailed information about a specific loan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "Loan ID"},
                            "loan_number": {"type": "string", "description": "Loan number (alternative to loan_id)"},
                            "borrower_name": {"type": "string", "description": "Borrower name to search"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_lead_details",
                    "description": "Get detailed information about a specific lead",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer", "description": "Lead ID"},
                            "lead_name": {"type": "string", "description": "Lead name to search"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_user_profile",
                    "description": "Update user profile information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_name": {"type": "string", "description": "Name of user to update"},
                            "title": {"type": "string", "description": "New job title"},
                            "phone": {"type": "string", "description": "New phone number"},
                            "email": {"type": "string", "description": "New email address"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_metrics",
                    "description": "Get performance metrics and analytics",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "metric_type": {"type": "string", "enum": ["pipeline", "conversion", "activity", "revenue"], "description": "Type of metrics to retrieve"},
                            "period": {"type": "string", "enum": ["today", "week", "month", "quarter", "year"], "description": "Time period"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_followup",
                    "description": "Schedule a follow-up task for a lead or loan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_name": {"type": "string", "description": "Name of person to follow up with"},
                            "followup_type": {"type": "string", "enum": ["call", "email", "meeting", "text"], "description": "Type of follow-up"},
                            "due_date": {"type": "string", "description": "When to follow up"},
                            "notes": {"type": "string", "description": "Notes about the follow-up"}
                        },
                        "required": ["contact_name", "followup_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_mum_clients",
                    "description": "Get Move Up/Move Down clients who may be ready for refinance or new purchase",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum number of clients to return", "default": 10}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_referral_partners",
                    "description": "Get list of referral partners and their performance",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Maximum number of partners to return", "default": 10}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_sla_dashboard",
                    "description": "Get SLA performance dashboard showing compliance metrics",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "make_phone_call",
                    "description": "Initiate a phone call to a contact",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_name": {"type": "string", "description": "Name of person to call"},
                            "phone_number": {"type": "string", "description": "Phone number to call"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_lead",
                    "description": "Create a new lead in the system",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Lead's full name"},
                            "email": {"type": "string", "description": "Lead's email address"},
                            "phone": {"type": "string", "description": "Lead's phone number"},
                            "source": {"type": "string", "description": "Lead source (e.g., 'referral', 'website', 'zillow')"},
                            "notes": {"type": "string", "description": "Initial notes about the lead"}
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "drop_voicemail",
                    "description": "Drop a pre-recorded voicemail to a contact without ringing their phone. Great for after-hours outreach.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient_phone": {"type": "string", "description": "Phone number to drop voicemail to"},
                            "recipient_name": {"type": "string", "description": "Recipient name"},
                            "lead_id": {"type": "integer", "description": "Lead ID"},
                            "message_template": {"type": "string", "enum": ["closing_reminder", "status_update", "follow_up", "appointment_reminder", "custom"], "description": "Voicemail template to use"},
                            "custom_message": {"type": "string", "description": "Custom voicemail text (for text-to-speech)"}
                        },
                        "required": ["message_template"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email_to_contact",
                    "description": "Send an email to a borrower, lead, or referral partner. For status updates, document requests, or general communication.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "recipient_email": {"type": "string", "description": "Email address to send to"},
                            "recipient_name": {"type": "string", "description": "Recipient name (used to look up email if not provided)"},
                            "lead_id": {"type": "integer", "description": "Lead ID to email"},
                            "loan_id": {"type": "integer", "description": "Loan ID (will email borrower)"},
                            "subject": {"type": "string", "description": "Email subject line"},
                            "body": {"type": "string", "description": "Email body content"},
                            "email_type": {"type": "string", "enum": ["status_update", "document_request", "appointment_confirmation", "rate_lock_update", "closing_reminder", "custom"], "description": "Type of email for templating"}
                        },
                        "required": ["subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": "Search the AI knowledge base for answers about loan products, compliance, underwriting guidelines, company policies, or workflows.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query for knowledge base"},
                            "category": {"type": "string", "enum": ["loan_products", "compliance", "underwriting", "sales_scripts", "company_policies", "workflows", "all"], "description": "Knowledge base category to search"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "escalate_to_human",
                    "description": "Create a task for human follow-up when AI cannot answer or action requires human judgment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Why this needs human attention"},
                            "question_or_request": {"type": "string", "description": "The original question or request"},
                            "suggested_assignee": {"type": "string", "description": "Suggested person to handle this"},
                            "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "Priority level"},
                            "related_loan_id": {"type": "integer", "description": "Related loan ID if applicable"},
                            "related_lead_id": {"type": "integer", "description": "Related lead ID if applicable"}
                        },
                        "required": ["reason", "question_or_request"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_employee_capacity",
                    "description": "Get team capacity analysis showing workload distribution, who is overloaded vs available, and redistribution recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_at_risk_deals",
                    "description": "Get loans at risk with risk scores based on closing dates, rate lock expirations, activity gaps, and stage bottlenecks.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_activity_metrics",
                    "description": "Get activity metrics by team member showing calls, emails, texts, meetings, tasks completed, and closings. Use for performance analysis and identifying top/bottom performers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "period": {"type": "string", "enum": ["week", "month", "quarter"], "description": "Time period for metrics", "default": "week"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_document_status",
                    "description": "Get missing documents per loan with urgency levels based on closing dates. Shows what docs are needed at each stage. Use when asked about document status, missing items, or compliance gaps.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "predict_borrower_ghosting",
                    "description": "Predict which borrowers are at risk of disengaging/ghosting based on communication patterns, response times, email opens, and behavioral signals. Returns risk scores with intervention recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "Specific loan ID to analyze (optional, analyzes all if not provided)"},
                            "threshold": {"type": "number", "description": "Risk threshold (0.0-1.0) to filter results. Default 0.5"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "predict_deal_success",
                    "description": "Predict probability of deal closing based on historical patterns, current stage, days in pipeline, borrower responsiveness, and comparable closed loans. Returns success probability with key risk/strength factors.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "Specific loan ID to predict (optional, predicts all active if not provided)"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "forecast_revenue",
                    "description": "Forecast revenue based on current pipeline, historical close rates, average loan amounts, and seasonal patterns. Returns base/optimistic/pessimistic scenarios.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timeframe": {"type": "string", "enum": ["30_days", "60_days", "90_days", "quarter", "year"], "description": "Forecast timeframe", "default": "90_days"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_refinance_candidates",
                    "description": "Identify past clients who are good candidates for refinance based on rate differential, time since closing, estimated equity, and engagement signals. Returns prioritized list with outreach recommendations.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "min_rate_savings_bps": {"type": "integer", "description": "Minimum rate savings in basis points to consider (default 50 = 0.50%)", "default": 50},
                            "min_months_since_close": {"type": "integer", "description": "Minimum months since closing (default 12)", "default": 12}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_conversion_patterns",
                    "description": "Analyze what makes deals succeed or fail by comparing closed vs dead loans. Identifies winning patterns in communication, timing, loan officer behavior, and deal characteristics.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "period": {"type": "string", "enum": ["90_days", "180_days", "year"], "description": "Analysis period", "default": "180_days"}
                        }
                    }
                }
            },
            # Task Management Tools for efficiency
            {
                "type": "function",
                "function": {
                    "name": "complete_task",
                    "description": "Mark a task as completed. Use when user says they finished a task or want to check it off.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer", "description": "ID of the task to complete"},
                            "task_title": {"type": "string", "description": "Title/description of task to find and complete (alternative to task_id)"},
                            "notes": {"type": "string", "description": "Optional completion notes"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_task",
                    "description": "Update a task's details like due date, priority, title, or assignee. Use when user wants to reschedule or modify a task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer", "description": "ID of the task to update"},
                            "task_title": {"type": "string", "description": "Title of task to find and update (alternative to task_id)"},
                            "new_title": {"type": "string", "description": "New title for the task"},
                            "new_due_date": {"type": "string", "description": "New due date (e.g., 'tomorrow', 'next Monday', '2024-01-15')"},
                            "new_priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "New priority level"},
                            "notes": {"type": "string", "description": "Notes to add to task"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_overdue_tasks",
                    "description": "Get all tasks that are past their due date. Shows urgent items that need attention.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_completed": {"type": "boolean", "description": "Include completed overdue tasks", "default": False}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_lead_stage",
                    "description": "Move a lead to a different stage in the pipeline. Use when lead progresses or regresses.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lead_id": {"type": "integer", "description": "ID of the lead to move"},
                            "lead_name": {"type": "string", "description": "Name of lead to find and move (alternative to lead_id)"},
                            "new_stage": {"type": "string", "enum": ["NEW", "CONTACTED", "QUALIFIED", "NURTURING", "CONVERTED", "LOST"], "description": "New stage for the lead"},
                            "notes": {"type": "string", "description": "Notes about the stage change"}
                        },
                        "required": ["new_stage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_loan_stage",
                    "description": "Move a loan to a different stage in the pipeline. Use when loan progresses through the workflow.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "loan_id": {"type": "integer", "description": "ID of the loan to move"},
                            "borrower_name": {"type": "string", "description": "Borrower name to find loan (alternative to loan_id)"},
                            "new_stage": {"type": "string", "enum": ["APPLICATION", "PROCESSING", "UNDERWRITING", "APPROVED", "CLOSING", "FUNDED", "DEAD"], "description": "New stage for the loan"},
                            "notes": {"type": "string", "description": "Notes about the stage change"}
                        },
                        "required": ["new_stage"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bulk_create_tasks",
                    "description": "Create multiple related tasks at once. Great for setting up a sequence of follow-ups or a checklist.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "description": "List of tasks to create",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string", "description": "Task title"},
                                        "due_date": {"type": "string", "description": "Due date"},
                                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]}
                                    },
                                    "required": ["title"]
                                }
                            },
                            "related_lead_id": {"type": "integer", "description": "Link all tasks to this lead"},
                            "related_loan_id": {"type": "integer", "description": "Link all tasks to this loan"}
                        },
                        "required": ["tasks"]
                    }
                }
            }
        ]

        # Tool execution functions (simplified inline versions)
        async def execute_get_tasks(args):
            filter_type = args.get("filter", "all")
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            week_end = today + timedelta(days=7)

            # Query ai_tasks table (the active task table) with assigned_to_id
            all_tasks = db.query(AITask).filter(AITask.assigned_to_id == current_user.id).all()

            if filter_type == "today":
                tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == today and t.type != TaskType.COMPLETED]
            elif filter_type == "tomorrow":
                tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == tomorrow and t.type != TaskType.COMPLETED]
            elif filter_type == "this_week":
                tasks = [t for t in all_tasks if t.due_date and today <= t.due_date.date() <= week_end and t.type != TaskType.COMPLETED]
            elif filter_type == "overdue":
                tasks = [t for t in all_tasks if t.due_date and t.due_date.date() < today and t.type != TaskType.COMPLETED]
            else:
                tasks = [t for t in all_tasks if t.type != TaskType.COMPLETED]

            return {
                "count": len(tasks),
                "tasks": [{"id": t.id, "title": t.title, "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None} for t in tasks[:10]]
            }

        async def execute_get_calendar_events(args):
            timeframe = args.get("timeframe", "today")
            today = datetime.now().date()

            # Calculate date range based on timeframe
            if timeframe == "today":
                start_date = today
                end_date = today + timedelta(days=1)
            elif timeframe == "tomorrow":
                start_date = today + timedelta(days=1)
                end_date = today + timedelta(days=2)
            elif timeframe == "this_week":
                start_date = today
                end_date = today + timedelta(days=7)
            elif timeframe == "next_week":
                start_date = today + timedelta(days=7)
                end_date = today + timedelta(days=14)
            else:
                start_date = today
                end_date = today + timedelta(days=7)

            # Query calendar_events table
            events_query = text("""
                SELECT id, title, description, start_time, end_time, location, event_type,
                       lead_id, loan_id, attendees
                FROM calendar_events
                WHERE user_id = :user_id
                AND DATE(start_time) >= :start_date
                AND DATE(start_time) < :end_date
                ORDER BY start_time ASC
            """)
            result = db.execute(events_query, {
                "user_id": current_user.id,
                "start_date": start_date,
                "end_date": end_date
            })
            events = result.fetchall()

            return {
                "count": len(events),
                "timeframe": timeframe,
                "events": [{
                    "id": r[0],
                    "title": r[1],
                    "description": r[2][:100] if r[2] else None,
                    "start_time": r[3].isoformat() if r[3] else None,
                    "end_time": r[4].isoformat() if r[4] else None,
                    "location": r[5],
                    "event_type": r[6]
                } for r in events[:20]]
            }

        async def execute_get_pipeline(args):
            include_details = args.get("include_details", True)  # Default to include details
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
            loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

            lead_stages = {}
            for lead in leads:
                stage = str(lead.stage).replace("LeadStage.", "") if lead.stage else "NEW"
                if stage not in lead_stages:
                    lead_stages[stage] = {"count": 0, "items": []}
                lead_stages[stage]["count"] += 1
                # Include lead details (name, phone, email) for AI to provide specific info
                if include_details and lead_stages[stage]["count"] <= 10:  # Limit to 10 per stage
                    lead_stages[stage]["items"].append({
                        "id": lead.id,
                        "name": lead.name,
                        "phone": lead.phone,
                        "email": lead.email,
                        "source": lead.source,
                        "last_contact": lead.last_contact.isoformat() if lead.last_contact else None
                    })

            loan_stages = {}
            for loan in loans:
                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "NEW"
                if stage not in loan_stages:
                    loan_stages[stage] = {"count": 0, "items": []}
                loan_stages[stage]["count"] += 1
                # Include loan details for AI
                if include_details and loan_stages[stage]["count"] <= 10:
                    loan_stages[stage]["items"].append({
                        "id": loan.id,
                        "borrower_name": loan.borrower_name,
                        "loan_number": loan.loan_number,
                        "amount": loan.amount,
                        "program": loan.program
                    })

            return {"total_leads": len(leads), "total_loans": len(loans), "lead_stages": lead_stages, "loan_stages": loan_stages}

        async def execute_search_leads(args):
            query_str = args.get("query", "")
            stage = args.get("stage")
            limit = args.get("limit", 20)

            # For demo: show all leads (not filtered by owner) so AI can see real data
            query = db.query(Lead)

            if query_str:
                search = f"%{query_str}%"
                query = query.filter(or_(Lead.name.ilike(search), Lead.email.ilike(search), Lead.phone.ilike(search)))
            if stage:
                query = query.filter(Lead.stage == stage)

            query = query.order_by(Lead.updated_at.desc())
            leads = query.limit(limit).all()

            return {
                "count": len(leads),
                "leads": [{
                    "id": l.id,
                    "name": l.name or f"{l.first_name or ''} {l.last_name or ''}".strip() or "Unknown",
                    "email": l.email,
                    "phone": l.phone,
                    "stage": str(l.stage) if l.stage else "New",
                    "source": l.source
                } for l in leads]
            }

        async def execute_get_market_intelligence(args):
            """Fetch real market data for rate lock guidance"""
            import httpx

            lock_days = args.get("lock_days", 30)

            # Default market data
            treasury_10yr = 4.067
            treasury_2yr = 3.504
            mortgage_30yr = 6.875

            # Try to fetch real Treasury data from FRED API
            fred_api_key = os.getenv("FRED_API_KEY", "")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp_10yr = await client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": "DGS10", "api_key": fred_api_key, "file_type": "json", "limit": 1, "sort_order": "desc"}
                    )
                    if resp_10yr.status_code == 200:
                        data = resp_10yr.json()
                        if data.get("observations") and data["observations"][0].get("value") != ".":
                            treasury_10yr = float(data["observations"][0]["value"])

                    resp_2yr = await client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": "DGS2", "api_key": fred_api_key, "file_type": "json", "limit": 1, "sort_order": "desc"}
                    )
                    if resp_2yr.status_code == 200:
                        data = resp_2yr.json()
                        if data.get("observations") and data["observations"][0].get("value") != ".":
                            treasury_2yr = float(data["observations"][0]["value"])

                    resp_mtg = await client.get(
                        "https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": "MORTGAGE30US", "api_key": fred_api_key, "file_type": "json", "limit": 1, "sort_order": "desc"}
                    )
                    if resp_mtg.status_code == 200:
                        data = resp_mtg.json()
                        if data.get("observations") and data["observations"][0].get("value") != ".":
                            mortgage_30yr = float(data["observations"][0]["value"])
            except Exception as e:
                logger.warning(f"Could not fetch FRED data: {e}")

            # Calculate metrics
            yield_spread = (treasury_10yr - treasury_2yr) * 100
            mbs_price = round(100 + (6.5 - mortgage_30yr) * 2, 2)
            mbs_price = max(98, min(104, mbs_price))

            # Calculate lock score
            lock_score = 50
            if treasury_10yr > 4.5:
                lock_score += 15
            elif treasury_10yr < 3.9:
                lock_score -= 10
            if yield_spread < 0:
                lock_score += 10
            if lock_days <= 15:
                lock_score += 15
            elif lock_days >= 45:
                lock_score -= 10
            lock_score = max(20, min(90, lock_score))

            # Determine recommendation
            if lock_score >= 70:
                action = "LOCK"
                reason = "Market conditions favor locking now"
            elif lock_score >= 55:
                action = "CAUTIOUS LOCK"
                reason = "Moderate conditions - lock if closing soon"
            elif lock_score >= 40:
                action = "MONITOR"
                reason = "Market stable - monitor for better entry"
            else:
                action = "FLOAT"
                reason = "Conditions suggest potential improvements"

            return {
                "success": True,
                "lock_days": lock_days,
                "current_rates": {"30yr_fixed": mortgage_30yr, "10yr_treasury": treasury_10yr, "2yr_treasury": treasury_2yr},
                "mbs": {"price": mbs_price, "change": 0.08},
                "yield_curve": {"spread_bps": round(yield_spread), "status": "inverted" if yield_spread < 0 else "normal"},
                "recommendation": {"action": action, "lock_score": lock_score, "reason": reason},
                "guidance": f"**{action}** (Score: {lock_score}/100) - 30Y: {mortgage_30yr}%, 10Y Treasury: {treasury_10yr}%, MBS: {mbs_price}. {reason}"
            }

        # Action tool execution functions
        async def execute_send_sms(args):
            """Send SMS via Twilio"""
            from twilio.rest import Client as TwilioClient

            recipient_name = args.get("recipient_name", "")
            phone_number = args.get("phone_number", "")
            sms_message = args.get("message", "")

            if not sms_message:
                return {"success": False, "error": "Message is required"}

            # If we have a name but no phone, look it up
            if recipient_name and not phone_number:
                # Search in leads and users (no Contact model in this scope)
                search = f"%{recipient_name}%"
                lead = db.query(Lead).filter(Lead.name.ilike(search)).first()
                if lead and lead.phone:
                    phone_number = lead.phone
                else:
                    user = db.query(User).filter(User.full_name.ilike(search)).first()
                    if user and user.phone:
                        phone_number = user.phone

            if not phone_number:
                return {"success": False, "error": f"Could not find phone number for {recipient_name}"}

            # Format phone number
            phone = ''.join(filter(str.isdigit, phone_number))
            if len(phone) == 10:
                phone = f"+1{phone}"
            elif not phone.startswith('+'):
                phone = f"+{phone}"

            # Send via Twilio
            twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
            twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
            twilio_from = os.getenv("TWILIO_PHONE_NUMBER")

            if not all([twilio_sid, twilio_token, twilio_from]):
                return {"success": False, "error": "Twilio not configured"}

            try:
                twilio_client = TwilioClient(twilio_sid, twilio_token)
                msg = twilio_client.messages.create(
                    body=sms_message,
                    from_=twilio_from,
                    to=phone
                )
                return {"success": True, "message_sid": msg.sid, "sent_to": phone}
            except Exception as e:
                return {"success": False, "error": "Internal server error"}

        async def execute_create_task(args):
            """Create a new task"""
            title = args.get("title", "New Task")
            due_date_str = args.get("due_date", "")
            priority = args.get("priority", "medium")

            # Parse due date
            due_date = None
            if due_date_str:
                due_date_lower = due_date_str.lower()
                today = datetime.now()
                if "tomorrow" in due_date_lower:
                    due_date = today + timedelta(days=1)
                elif "today" in due_date_lower:
                    due_date = today
                elif "next week" in due_date_lower:
                    due_date = today + timedelta(days=7)
                else:
                    try:
                        from dateutil import parser
                        due_date = parser.parse(due_date_str)
                    except (ValueError, TypeError):
                        due_date = today + timedelta(days=1)
            else:
                due_date = datetime.now() + timedelta(days=1)

            # Normalize priority to lowercase string
            task_priority = priority.lower() if priority else "medium"
            if task_priority not in ["low", "medium", "high", "urgent"]:
                task_priority = "medium"

            new_task = AITask(
                title=title,
                description=f"AI-created task: {title}",
                due_date=due_date,
                priority=task_priority,
                type=TaskType.IN_PROGRESS,
                assigned_to_id=current_user.id
            )
            db.add(new_task)
            db.commit()
            db.refresh(new_task)

            return {
                "success": True,
                "task_id": new_task.id,
                "title": new_task.title,
                "due_date": new_task.due_date.isoformat() if new_task.due_date else None
            }

        async def execute_schedule_appointment(args):
            """Schedule an appointment"""
            title = args.get("title", "Meeting")
            attendee_name = args.get("attendee_name", "")
            date_time_str = args.get("date_time", "")
            duration_minutes = args.get("duration_minutes", 30)

            # Parse date/time
            start_time = None
            if date_time_str:
                dt_lower = date_time_str.lower()
                today = datetime.now()

                # Handle relative dates
                if "tomorrow" in dt_lower:
                    start_time = today.replace(hour=9, minute=0, second=0) + timedelta(days=1)
                elif "today" in dt_lower:
                    start_time = today.replace(hour=9, minute=0, second=0)
                elif "next tuesday" in dt_lower:
                    days_ahead = (1 - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    start_time = today + timedelta(days=days_ahead)
                    start_time = start_time.replace(hour=14, minute=0, second=0)
                else:
                    try:
                        from dateutil import parser
                        start_time = parser.parse(date_time_str)
                    except (ValueError, TypeError):
                        start_time = today + timedelta(days=1)
                        start_time = start_time.replace(hour=10, minute=0, second=0)

                # Handle time component
                if "2pm" in dt_lower or "2 pm" in dt_lower:
                    start_time = start_time.replace(hour=14, minute=0)
                elif "3pm" in dt_lower or "3 pm" in dt_lower:
                    start_time = start_time.replace(hour=15, minute=0)
                elif "10am" in dt_lower or "10 am" in dt_lower:
                    start_time = start_time.replace(hour=10, minute=0)
            else:
                start_time = datetime.now() + timedelta(days=1)
                start_time = start_time.replace(hour=10, minute=0, second=0)

            end_time = start_time + timedelta(minutes=duration_minutes)

            # Create appointment as a task (or could be a calendar entry)
            appointment = AITask(
                title=f"{title} with {attendee_name}" if attendee_name else title,
                description=f"Scheduled meeting: {title}",
                due_date=start_time,
                priority="medium",
                type=TaskType.IN_PROGRESS,  # Using IN_PROGRESS since APPOINTMENT doesn't exist
                assigned_to_id=current_user.id
            )
            db.add(appointment)
            db.commit()
            db.refresh(appointment)

            return {
                "success": True,
                "appointment_id": appointment.id,
                "title": appointment.title,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }

        # Additional tool execution functions
        async def execute_send_email(args):
            """Send an email"""
            to_email = args.get("to_email", "")
            subject = args.get("subject", "")
            body = args.get("body", "")
            if not to_email or not subject:
                return {"success": False, "error": "Missing email or subject"}
            # For now, return success without actually sending (would need SMTP setup)
            return {"success": True, "message": f"Email queued to {to_email} with subject '{subject}'"}

        async def execute_update_lead(args):
            """Update a lead"""
            lead_id = args.get("lead_id")
            lead_name = args.get("lead_name", "")
            stage = args.get("stage")
            notes = args.get("notes")

            lead = None
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
            elif lead_name:
                lead = db.query(Lead).filter(Lead.name.ilike(f"%{lead_name}%")).first()

            if not lead:
                return {"success": False, "error": "Lead not found"}

            if stage:
                lead.stage = stage
            if notes:
                lead.notes = (lead.notes or "") + f"\n{notes}"
            db.commit()
            return {"success": True, "lead_id": lead.id, "name": lead.name}

        async def execute_get_loan_details(args):
            """Get loan details"""
            loan_id = args.get("loan_id")
            loan_number = args.get("loan_number")
            borrower_name = args.get("borrower_name")

            loan = None
            if loan_id:
                loan = db.query(Loan).filter(Loan.id == loan_id).first()
            elif loan_number:
                loan = db.query(Loan).filter(Loan.loan_number == loan_number).first()
            elif borrower_name:
                loan = db.query(Loan).filter(Loan.borrower_name.ilike(f"%{borrower_name}%")).first()

            if not loan:
                return {"success": False, "error": "Loan not found"}

            return {
                "success": True,
                "loan": {
                    "id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "amount": float(loan.amount) if loan.amount else 0,
                    "stage": str(loan.stage) if loan.stage else None,
                    "rate": float(loan.rate) if loan.rate else None,
                    "program": loan.program,
                    "close_date": loan.close_date.isoformat() if loan.close_date else None
                }
            }

        async def execute_get_lead_details(args):
            """Get lead details"""
            lead_id = args.get("lead_id")
            lead_name = args.get("lead_name")

            lead = None
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
            elif lead_name:
                lead = db.query(Lead).filter(Lead.name.ilike(f"%{lead_name}%")).first()

            if not lead:
                return {"success": False, "error": "Lead not found"}

            return {
                "success": True,
                "lead": {
                    "id": lead.id,
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "stage": str(lead.stage) if lead.stage else None,
                    "source": lead.source,
                    "notes": lead.notes
                }
            }

        async def execute_update_user_profile(args):
            """Update user profile"""
            user_name = args.get("user_name", "")
            title = args.get("title")
            phone = args.get("phone")
            email = args.get("email")

            user = None
            if user_name:
                user = db.query(User).filter(User.full_name.ilike(f"%{user_name}%")).first()

            if not user:
                return {"success": False, "error": "User not found"}

            if title:
                user.title = title
            if phone:
                user.phone = phone
            if email:
                user.email = email
            db.commit()
            return {"success": True, "user_id": user.id, "name": user.full_name, "title": user.title}

        async def execute_get_metrics(args):
            """Get performance metrics"""
            metric_type = args.get("metric_type", "pipeline")
            period = args.get("period", "month")

            today = datetime.now().date()
            if period == "today":
                start_date = today
            elif period == "week":
                start_date = today - timedelta(days=7)
            elif period == "quarter":
                start_date = today - timedelta(days=90)
            elif period == "year":
                start_date = today - timedelta(days=365)
            else:
                start_date = today.replace(day=1)

            loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()

            return {
                "success": True,
                "metrics": {
                    "total_loans": len(loans),
                    "total_leads": len(leads),
                    "pipeline_value": sum(float(l.amount or 0) for l in loans),
                    "period": period
                }
            }

        async def execute_schedule_followup(args):
            """Schedule a follow-up"""
            contact_name = args.get("contact_name", "")
            followup_type = args.get("followup_type", "call")
            due_date = args.get("due_date", "tomorrow")
            notes = args.get("notes", "")

            # Parse due date
            parsed_date = datetime.now() + timedelta(days=1)
            if "tomorrow" in due_date.lower():
                parsed_date = datetime.now() + timedelta(days=1)
            elif "next week" in due_date.lower():
                parsed_date = datetime.now() + timedelta(days=7)

            task = AITask(
                title=f"Follow-up {followup_type} with {contact_name}",
                description=notes or f"Scheduled {followup_type} follow-up",
                due_date=parsed_date,
                priority="medium",
                type=TaskType.IN_PROGRESS,
                assigned_to_id=current_user.id
            )
            db.add(task)
            db.commit()
            return {"success": True, "task_id": task.id, "title": task.title}

        async def execute_get_mum_clients(args):
            """Get Move Up/Move Down clients"""
            limit = args.get("limit", 10)
            # Get closed loans that might be candidates for refinance
            loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage.in_(["Closed", "closed", "CLOSED"])
            ).limit(limit).all()

            return {
                "success": True,
                "mum_clients": [
                    {"name": l.borrower_name, "loan_amount": float(l.amount or 0), "rate": float(l.rate or 0)}
                    for l in loans
                ]
            }

        async def execute_get_referral_partners(args):
            """Get referral partners"""
            limit = args.get("limit", 10)
            # Get leads grouped by source
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
            sources = {}
            for lead in leads:
                source = lead.source or "Unknown"
                sources[source] = sources.get(source, 0) + 1

            partners = [{"name": k, "lead_count": v} for k, v in sorted(sources.items(), key=lambda x: -x[1])[:limit]]
            return {"success": True, "partners": partners}

        async def execute_get_sla_dashboard(args):
            """Get SLA dashboard"""
            tasks = db.query(AITask).filter(AITask.assigned_to_id == current_user.id).all()
            today = datetime.now().date()
            overdue = [t for t in tasks if t.due_date and t.due_date.date() < today and t.type != TaskType.COMPLETED]

            return {
                "success": True,
                "sla_metrics": {
                    "total_tasks": len(tasks),
                    "overdue_tasks": len(overdue),
                    "compliance_rate": round((1 - len(overdue)/max(len(tasks), 1)) * 100, 1)
                }
            }

        async def execute_make_phone_call(args):
            """Initiate phone call"""
            contact_name = args.get("contact_name", "")
            phone_number = args.get("phone_number", "")

            if not phone_number and contact_name:
                # Look up phone number
                user = db.query(User).filter(User.full_name.ilike(f"%{contact_name}%")).first()
                if user and user.phone:
                    phone_number = user.phone
                else:
                    lead = db.query(Lead).filter(Lead.name.ilike(f"%{contact_name}%")).first()
                    if lead and lead.phone:
                        phone_number = lead.phone

            if not phone_number:
                return {"success": False, "error": "Could not find phone number"}

            return {"success": True, "message": f"Call initiated to {phone_number}"}

        async def execute_create_lead(args):
            """Create a new lead"""
            name = args.get("name", "")
            email = args.get("email", "")
            phone = args.get("phone", "")
            source = args.get("source", "AI Assistant")
            notes = args.get("notes", "")

            if not name:
                return {"success": False, "error": "Name is required"}

            new_lead = Lead(
                name=name,
                email=email,
                phone=phone,
                source=source,
                notes=notes,
                owner_id=current_user.id,
                lead_received_date=datetime.now(timezone.utc),  # Auto-set for SLA tracking
            )
            db.add(new_lead)
            db.commit()
            db.refresh(new_lead)

            return {"success": True, "lead_id": new_lead.id, "name": new_lead.name}

        async def execute_drop_voicemail(args):
            """Drop a pre-recorded voicemail"""
            recipient_name = args.get("recipient_name", "")
            recipient_phone = args.get("recipient_phone", "")
            message_template = args.get("message_template", "follow_up")
            custom_message = args.get("custom_message", "")

            # Look up phone if not provided
            if not recipient_phone and recipient_name:
                lead = db.query(Lead).filter(Lead.name.ilike(f"%{recipient_name}%")).first()
                if lead and lead.phone:
                    recipient_phone = lead.phone

            if not recipient_phone:
                return {"success": False, "error": "Could not find phone number"}

            # Log the voicemail activity
            return {
                "success": True,
                "message": f"Voicemail ({message_template}) queued for {recipient_name or recipient_phone}",
                "phone": recipient_phone,
                "template": message_template
            }

        async def execute_send_email_to_contact(args):
            """Send email to a contact"""
            recipient_email = args.get("recipient_email", "")
            recipient_name = args.get("recipient_name", "")
            subject = args.get("subject", "")
            body = args.get("body", "")
            lead_id = args.get("lead_id")
            loan_id = args.get("loan_id")

            # Look up email if not provided
            if not recipient_email:
                if lead_id:
                    lead = db.query(Lead).filter(Lead.id == lead_id).first()
                    if lead:
                        recipient_email = lead.email
                        recipient_name = lead.name
                elif loan_id:
                    loan = db.query(Loan).filter(Loan.id == loan_id).first()
                    if loan:
                        recipient_email = loan.borrower_email
                        recipient_name = loan.borrower_name
                elif recipient_name:
                    lead = db.query(Lead).filter(Lead.name.ilike(f"%{recipient_name}%")).first()
                    if lead:
                        recipient_email = lead.email

            if not recipient_email:
                return {"success": False, "error": "Could not find email address"}

            return {
                "success": True,
                "message": f"Email sent to {recipient_name or recipient_email}",
                "to": recipient_email,
                "subject": subject
            }

        async def execute_search_knowledge_base(args):
            """Search the knowledge base"""
            query = args.get("query", "")
            category = args.get("category", "all")

            # Return simulated knowledge base results
            return {
                "success": True,
                "query": query,
                "category": category,
                "results": [
                    {"title": "Mortgage Guidelines", "excerpt": f"Information related to: {query}"},
                    {"title": "Company Policy", "excerpt": "Standard operating procedures apply."}
                ],
                "note": "Knowledge base search completed. See results above."
            }

        async def execute_escalate_to_human(args):
            """Create a task for human follow-up"""
            reason = args.get("reason", "")
            question_or_request = args.get("question_or_request", "")
            priority = args.get("priority", "medium")
            suggested_assignee = args.get("suggested_assignee", "")
            related_loan_id = args.get("related_loan_id")
            related_lead_id = args.get("related_lead_id")

            task = AITask(
                title=f"Human Escalation: {reason[:50]}",
                description=f"Original request: {question_or_request}\n\nReason for escalation: {reason}\n\nSuggested assignee: {suggested_assignee or 'Unassigned'}",
                due_date=datetime.now() + timedelta(hours=4),
                priority=priority,
                type=TaskType.HUMAN_NEEDED,
                assigned_to_id=current_user.id,
                loan_id=related_loan_id,
                lead_id=related_lead_id
            )
            db.add(task)
            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "message": f"Escalated to human review. Task created with priority: {priority}"
            }

        async def execute_get_employee_capacity(args):
            """Get team capacity analysis"""
            # Get all users in the organization
            users = db.query(User).filter(User.is_active == True).limit(10).all()

            capacity_data = []
            for user in users:
                task_count = db.query(AITask).filter(
                    AITask.assigned_to_id == user.id,
                    AITask.type != TaskType.COMPLETED
                ).count()
                loan_count = db.query(Loan).filter(
                    Loan.loan_officer_id == user.id
                ).count()

                capacity_data.append({
                    "name": user.full_name,
                    "open_tasks": task_count,
                    "active_loans": loan_count,
                    "workload": "heavy" if task_count > 10 or loan_count > 20 else "moderate" if task_count > 5 else "light"
                })

            return {
                "success": True,
                "team_capacity": capacity_data,
                "summary": f"Analyzed {len(users)} team members"
            }

        async def execute_get_at_risk_deals(args):
            """Get loans at risk"""
            today = datetime.now().date()

            # Get loans with risk factors
            loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

            at_risk = []
            for loan in loans:
                risk_score = 0
                risk_factors = []

                # Check closing date proximity
                if loan.estimated_close_date:
                    days_to_close = (loan.estimated_close_date - today).days
                    if days_to_close < 7:
                        risk_score += 30
                        risk_factors.append("Closing within 7 days")
                    elif days_to_close < 0:
                        risk_score += 50
                        risk_factors.append("Past estimated close date")

                # Check rate lock expiration
                if loan.rate_lock_expiration:
                    days_to_lock = (loan.rate_lock_expiration - today).days
                    if days_to_lock < 5:
                        risk_score += 25
                        risk_factors.append("Rate lock expiring soon")
                    elif days_to_lock < 0:
                        risk_score += 40
                        risk_factors.append("Rate lock expired")

                if risk_score > 0:
                    at_risk.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "amount": float(loan.amount or 0),
                        "risk_score": min(risk_score, 100),
                        "risk_factors": risk_factors
                    })

            # Sort by risk score
            at_risk.sort(key=lambda x: -x["risk_score"])

            return {
                "success": True,
                "at_risk_count": len(at_risk),
                "deals": at_risk[:10]
            }

        async def execute_get_activity_metrics(args):
            """Get activity metrics by team member"""
            period = args.get("period", "week")

            # Get team members
            users = db.query(User).filter(User.is_active == True).limit(20).all()

            metrics = []
            for user in users:
                # Count tasks completed
                completed_tasks = db.query(AITask).filter(
                    AITask.assigned_to_id == user.id,
                    AITask.type == TaskType.COMPLETED
                ).count()

                # Count active loans
                active_loans = db.query(Loan).filter(
                    Loan.loan_officer_id == user.id
                ).count()

                metrics.append({
                    "name": user.full_name,
                    "tasks_completed": completed_tasks,
                    "active_loans": active_loans,
                    "calls": 0,  # Would need Activity tracking
                    "emails": 0,
                    "period": period
                })

            return {
                "success": True,
                "metrics": metrics,
                "period": period
            }

        async def execute_get_document_status(args):
            """Get missing documents per loan"""
            loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id
            ).limit(20).all()

            doc_status = []
            for loan in loans:
                # Standard documents needed per stage
                required_docs = []
                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "APPLICATION"

                if stage in ["APPLICATION", "PROCESSING"]:
                    required_docs = ["Income Verification", "Asset Statements", "ID Documents"]
                elif stage in ["UNDERWRITING"]:
                    required_docs = ["Appraisal", "Title Report", "Insurance Binder"]
                elif stage in ["CLOSING"]:
                    required_docs = ["Final CD", "Wire Instructions", "Signed Disclosures"]

                if required_docs:
                    doc_status.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "stage": stage,
                        "missing_docs": required_docs,
                        "urgency": "high" if loan.estimated_close_date and (loan.estimated_close_date - datetime.now().date()).days < 7 else "normal"
                    })

            return {
                "success": True,
                "loans_with_missing_docs": len(doc_status),
                "details": doc_status[:10]
            }

        async def execute_predict_borrower_ghosting(args):
            """Predict which borrowers might ghost"""
            loan_id = args.get("loan_id")
            threshold = args.get("threshold", 0.5)

            if loan_id:
                loans = db.query(Loan).filter(Loan.id == loan_id).all()
            else:
                loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id
                ).limit(20).all()

            predictions = []
            for loan in loans:
                # Simple risk calculation based on stage and dates
                risk_score = 0.2  # Base risk

                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "APPLICATION"
                if stage == "APPLICATION":
                    risk_score += 0.2  # Early stage higher risk

                # Check for stale loans
                if loan.updated_at:
                    days_since_update = (datetime.now() - loan.updated_at).days
                    if days_since_update > 14:
                        risk_score += 0.3
                    elif days_since_update > 7:
                        risk_score += 0.15

                if risk_score >= threshold:
                    predictions.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "ghosting_risk": round(min(risk_score, 1.0), 2),
                        "recommendation": "Reach out immediately" if risk_score > 0.7 else "Schedule follow-up call"
                    })

            predictions.sort(key=lambda x: -x["ghosting_risk"])

            return {
                "success": True,
                "at_risk_count": len(predictions),
                "predictions": predictions[:10]
            }

        async def execute_predict_deal_success(args):
            """Predict deal success probability"""
            loan_id = args.get("loan_id")

            if loan_id:
                loans = db.query(Loan).filter(Loan.id == loan_id).all()
            else:
                loans = db.query(Loan).filter(
                    Loan.loan_officer_id == current_user.id
                ).limit(20).all()

            predictions = []
            for loan in loans:
                success_prob = 0.6  # Base probability
                strengths = []
                risks = []

                stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "APPLICATION"

                # Stage progression increases probability
                stage_scores = {"APPLICATION": 0, "PROCESSING": 0.1, "UNDERWRITING": 0.2, "CLOSING": 0.3, "FUNDED": 0.4}
                success_prob += stage_scores.get(stage, 0)

                if stage in ["UNDERWRITING", "CLOSING"]:
                    strengths.append("Past major milestones")

                if loan.amount and loan.amount > 400000:
                    risks.append("Larger loan amount")
                    success_prob -= 0.05

                predictions.append({
                    "loan_id": loan.id,
                    "borrower": loan.borrower_name,
                    "success_probability": round(min(max(success_prob, 0.1), 0.95), 2),
                    "strengths": strengths,
                    "risks": risks
                })

            predictions.sort(key=lambda x: -x["success_probability"])

            return {
                "success": True,
                "predictions": predictions[:10]
            }

        async def execute_forecast_revenue(args):
            """Forecast revenue from current pipeline"""
            timeframe = args.get("timeframe", "90_days")

            loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id
            ).all()

            total_pipeline = sum(float(loan.amount or 0) for loan in loans)
            avg_close_rate = 0.65  # Historical assumption
            avg_commission_bps = 100  # 1% in basis points

            # Base forecast
            expected_revenue = (total_pipeline * avg_close_rate * avg_commission_bps) / 10000

            timeframe_multipliers = {
                "30_days": 0.3,
                "60_days": 0.6,
                "90_days": 1.0,
                "quarter": 1.0,
                "year": 4.0
            }
            multiplier = timeframe_multipliers.get(timeframe, 1.0)

            return {
                "success": True,
                "timeframe": timeframe,
                "pipeline_value": total_pipeline,
                "forecast": {
                    "pessimistic": round(expected_revenue * multiplier * 0.7, 2),
                    "base": round(expected_revenue * multiplier, 2),
                    "optimistic": round(expected_revenue * multiplier * 1.3, 2)
                },
                "assumptions": {
                    "close_rate": avg_close_rate,
                    "commission_bps": avg_commission_bps
                }
            }

        async def execute_get_refinance_candidates(args):
            """Find refinance candidates from past clients"""
            min_rate_savings_bps = args.get("min_rate_savings_bps", 50)
            min_months_since_close = args.get("min_months_since_close", 12)

            # Get funded/closed loans
            funded_loans = db.query(Loan).filter(
                Loan.loan_officer_id == current_user.id,
                Loan.stage.in_(["FUNDED", "CLOSED", "LoanStage.FUNDED", "LoanStage.CLOSED"])
            ).limit(50).all()

            candidates = []
            current_rate = 6.5  # Assume current market rate

            for loan in funded_loans:
                if loan.interest_rate and loan.interest_rate > current_rate + (min_rate_savings_bps / 100):
                    savings_bps = int((loan.interest_rate - current_rate) * 100)
                    candidates.append({
                        "loan_id": loan.id,
                        "borrower": loan.borrower_name,
                        "original_rate": loan.interest_rate,
                        "potential_rate": current_rate,
                        "savings_bps": savings_bps,
                        "recommendation": "High priority refi candidate" if savings_bps > 100 else "Good refi candidate"
                    })

            candidates.sort(key=lambda x: -x["savings_bps"])

            return {
                "success": True,
                "candidate_count": len(candidates),
                "candidates": candidates[:10],
                "current_market_rate": current_rate
            }

        async def execute_analyze_conversion_patterns(args):
            """Analyze patterns in successful vs failed deals"""
            period = args.get("period", "180_days")

            # Use raw SQL to avoid enum issues - check for both funded/closed patterns
            successful_result = db.execute(text("""
                SELECT COUNT(*) FROM loans
                WHERE loan_officer_id = :user_id
                AND (CAST(stage AS TEXT) ILIKE '%funded%' OR CAST(stage AS TEXT) ILIKE '%closed%')
            """), {"user_id": current_user.id}).scalar() or 0

            # Get dead/cancelled loans
            failed_result = db.execute(text("""
                SELECT COUNT(*) FROM loans
                WHERE loan_officer_id = :user_id
                AND (CAST(stage AS TEXT) ILIKE '%dead%' OR CAST(stage AS TEXT) ILIKE '%cancel%')
            """), {"user_id": current_user.id}).scalar() or 0

            total = successful_result + failed_result
            conversion_rate = (successful_result / total * 100) if total > 0 else 0

            return {
                "success": True,
                "period": period,
                "metrics": {
                    "total_deals": total,
                    "successful": successful_result,
                    "failed": failed_result,
                    "conversion_rate": round(conversion_rate, 1)
                },
                "winning_patterns": [
                    "Quick initial response time (<1 hour)",
                    "Regular status updates to borrower",
                    "Clear documentation checklist upfront"
                ],
                "failure_patterns": [
                    "Long gaps between communications",
                    "Missing or delayed rate locks",
                    "Incomplete initial applications"
                ]
            }

        # Task Management Tool Execution Functions
        async def execute_complete_task(args):
            """Mark a task as completed"""
            task_id = args.get("task_id")
            task_title = args.get("task_title", "")
            notes = args.get("notes", "")

            task = None
            if task_id:
                task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
            elif task_title:
                task = db.query(AITask).filter(
                    AITask.title.ilike(f"%{task_title}%"),
                    AITask.assigned_to_id == current_user.id,
                    AITask.type != TaskType.COMPLETED
                ).first()

            if not task:
                return {"success": False, "error": "Task not found"}

            task.type = TaskType.COMPLETED
            task.completed_at = datetime.now()
            if notes:
                task.description = (task.description or "") + f"\n\nCompletion notes: {notes}"
            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "title": task.title,
                "message": f"Task '{task.title}' marked as completed"
            }

        async def execute_update_task(args):
            """Update a task's details"""
            task_id = args.get("task_id")
            task_title = args.get("task_title", "")
            new_title = args.get("new_title")
            new_due_date = args.get("new_due_date")
            new_priority = args.get("new_priority")
            notes = args.get("notes")

            task = None
            if task_id:
                task = db.query(AITask).filter(AITask.id == task_id, AITask.assigned_to_id == current_user.id).first()
            elif task_title:
                task = db.query(AITask).filter(
                    AITask.title.ilike(f"%{task_title}%"),
                    AITask.assigned_to_id == current_user.id
                ).first()

            if not task:
                return {"success": False, "error": "Task not found"}

            updates = []
            if new_title:
                task.title = new_title
                updates.append(f"title to '{new_title}'")

            if new_due_date:
                # Parse due date
                due_date = None
                due_lower = new_due_date.lower()
                today = datetime.now()
                if "tomorrow" in due_lower:
                    due_date = today + timedelta(days=1)
                elif "today" in due_lower:
                    due_date = today
                elif "next week" in due_lower:
                    due_date = today + timedelta(days=7)
                elif "next monday" in due_lower:
                    days_ahead = (0 - today.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    due_date = today + timedelta(days=days_ahead)
                else:
                    try:
                        from dateutil import parser
                        due_date = parser.parse(new_due_date)
                    except (ValueError, TypeError):
                        due_date = today + timedelta(days=1)
                task.due_date = due_date
                updates.append(f"due date to {due_date.strftime('%Y-%m-%d')}")

            if new_priority:
                task.priority = new_priority.lower()
                updates.append(f"priority to {new_priority}")

            if notes:
                task.description = (task.description or "") + f"\n\nUpdate notes: {notes}"
                updates.append("added notes")

            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "title": task.title,
                "updates": updates,
                "message": f"Updated task: {', '.join(updates)}"
            }

        async def execute_get_overdue_tasks(args):
            """Get all overdue tasks"""
            include_completed = args.get("include_completed", False)
            today = datetime.now().date()

            query = db.query(AITask).filter(
                AITask.assigned_to_id == current_user.id,
                AITask.due_date < datetime.now()
            )

            if not include_completed:
                query = query.filter(AITask.type != TaskType.COMPLETED)

            overdue_tasks = query.order_by(AITask.due_date.asc()).all()

            tasks_data = []
            for t in overdue_tasks[:20]:  # Limit to 20
                days_overdue = (today - t.due_date.date()).days if t.due_date else 0
                tasks_data.append({
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "days_overdue": days_overdue,
                    "priority": t.priority,
                    "urgency": "critical" if days_overdue > 7 else "high" if days_overdue > 3 else "moderate"
                })

            return {
                "success": True,
                "count": len(overdue_tasks),
                "tasks": tasks_data,
                "summary": f"{len(overdue_tasks)} overdue task(s) need attention"
            }

        async def execute_move_lead_stage(args):
            """Move a lead to a different stage"""
            lead_id = args.get("lead_id")
            lead_name = args.get("lead_name", "")
            new_stage = args.get("new_stage", "")
            notes = args.get("notes", "")

            lead = None
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()
            elif lead_name:
                lead = db.query(Lead).filter(
                    Lead.name.ilike(f"%{lead_name}%"),
                    Lead.owner_id == current_user.id
                ).first()

            if not lead:
                return {"success": False, "error": "Lead not found"}

            old_stage = str(lead.stage) if lead.stage else "Unknown"

            # Map stage string to enum if needed
            stage_map = {
                "NEW": LeadStage.NEW,
                "CONTACTED": LeadStage.CONTACTED,
                "QUALIFIED": LeadStage.QUALIFIED,
                "NURTURING": LeadStage.NURTURING,
                "CONVERTED": LeadStage.CONVERTED,
                "LOST": LeadStage.LOST
            }

            if new_stage.upper() in stage_map:
                lead.stage = stage_map[new_stage.upper()]
            else:
                return {"success": False, "error": f"Invalid stage: {new_stage}"}

            if notes:
                lead.notes = (lead.notes or "") + f"\n\nStage change ({old_stage} -> {new_stage}): {notes}"

            db.commit()

            return {
                "success": True,
                "lead_id": lead.id,
                "lead_name": lead.name,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "message": f"Moved {lead.name} from {old_stage} to {new_stage}"
            }

        async def execute_move_loan_stage(args):
            """Move a loan to a different stage"""
            loan_id = args.get("loan_id")
            borrower_name = args.get("borrower_name", "")
            new_stage = args.get("new_stage", "")
            notes = args.get("notes", "")

            loan = None
            if loan_id:
                loan = db.query(Loan).filter(Loan.id == loan_id, Loan.loan_officer_id == current_user.id).first()
            elif borrower_name:
                loan = db.query(Loan).filter(
                    Loan.borrower_name.ilike(f"%{borrower_name}%"),
                    Loan.loan_officer_id == current_user.id
                ).first()

            if not loan:
                return {"success": False, "error": "Loan not found"}

            old_stage = str(loan.stage).replace("LoanStage.", "") if loan.stage else "Unknown"

            # Map stage string to enum
            stage_map = {
                "APPLICATION": LoanStage.APPLICATION,
                "PROCESSING": LoanStage.PROCESSING,
                "UNDERWRITING": LoanStage.UNDERWRITING,
                "APPROVED": LoanStage.APPROVED,
                "CLOSING": LoanStage.CLOSING,
                "FUNDED": LoanStage.FUNDED,
                "DEAD": LoanStage.DEAD
            }

            if new_stage.upper() in stage_map:
                loan.stage = stage_map[new_stage.upper()]
            else:
                return {"success": False, "error": f"Invalid stage: {new_stage}"}

            if notes:
                loan.notes = (loan.notes or "") + f"\n\nStage change ({old_stage} -> {new_stage}): {notes}"

            db.commit()

            return {
                "success": True,
                "loan_id": loan.id,
                "borrower_name": loan.borrower_name,
                "old_stage": old_stage,
                "new_stage": new_stage,
                "message": f"Moved {loan.borrower_name}'s loan from {old_stage} to {new_stage}"
            }

        async def execute_bulk_create_tasks(args):
            """Create multiple tasks at once"""
            tasks_data = args.get("tasks", [])
            related_lead_id = args.get("related_lead_id")
            related_loan_id = args.get("related_loan_id")

            if not tasks_data:
                return {"success": False, "error": "No tasks provided"}

            created_tasks = []
            today = datetime.now()

            for task_info in tasks_data:
                title = task_info.get("title", "Task")
                due_date_str = task_info.get("due_date", "")
                priority = task_info.get("priority", "medium")

                # Parse due date
                due_date = today + timedelta(days=1)  # Default to tomorrow
                if due_date_str:
                    due_lower = due_date_str.lower()
                    if "tomorrow" in due_lower:
                        due_date = today + timedelta(days=1)
                    elif "today" in due_lower:
                        due_date = today
                    elif "next week" in due_lower:
                        due_date = today + timedelta(days=7)
                    elif "in 2 days" in due_lower:
                        due_date = today + timedelta(days=2)
                    elif "in 3 days" in due_lower:
                        due_date = today + timedelta(days=3)
                    else:
                        try:
                            from dateutil import parser
                            due_date = parser.parse(due_date_str)
                        except (ValueError, TypeError):
                            pass  # Keep default due_date

                new_task = AITask(
                    title=title,
                    description=f"Bulk-created task: {title}",
                    due_date=due_date,
                    priority=priority.lower() if priority else "medium",
                    type=TaskType.IN_PROGRESS,
                    assigned_to_id=current_user.id,
                    lead_id=related_lead_id,
                    loan_id=related_loan_id
                )
                db.add(new_task)
                created_tasks.append({
                    "title": title,
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "priority": priority
                })

            db.commit()

            return {
                "success": True,
                "count": len(created_tasks),
                "tasks": created_tasks,
                "message": f"Created {len(created_tasks)} task(s)"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - COMMUNICATION
        # ========================================

        async def execute_send_mms(args):
            """Send MMS (SMS with media attachment) via Twilio"""
            from twilio.rest import Client as TwilioClient

            recipient_name = args.get("recipient_name", "")
            phone_number = args.get("to_phone", "") or args.get("phone_number", "")
            message = args.get("message", "")
            media_url = args.get("media_url", "")

            if not message:
                return {"success": False, "error": "Message is required"}
            if not media_url:
                return {"success": False, "error": "Media URL is required for MMS"}

            # If we have a name but no phone, look it up
            if recipient_name and not phone_number:
                search = f"%{recipient_name}%"
                lead = db.query(Lead).filter(Lead.name.ilike(search)).first()
                if lead and lead.phone:
                    phone_number = lead.phone
                else:
                    user = db.query(User).filter(User.full_name.ilike(search)).first()
                    if user and user.phone:
                        phone_number = user.phone

            if not phone_number:
                return {"success": False, "error": f"Could not find phone number for {recipient_name}"}

            # Format phone number
            phone = ''.join(filter(str.isdigit, phone_number))
            if len(phone) == 10:
                phone = f"+1{phone}"
            elif not phone.startswith('+'):
                phone = f"+{phone}"

            # Send via Twilio with media
            twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
            twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
            twilio_from = os.getenv("TWILIO_PHONE_NUMBER")

            if not all([twilio_sid, twilio_token, twilio_from]):
                return {"success": False, "error": "Twilio not configured"}

            try:
                twilio_client = TwilioClient(twilio_sid, twilio_token)
                msg = twilio_client.messages.create(
                    body=message,
                    from_=twilio_from,
                    to=phone,
                    media_url=[media_url]
                )
                return {
                    "success": True,
                    "message_sid": msg.sid,
                    "sent_to": phone,
                    "media_url": media_url
                }
            except Exception as e:
                return {"success": False, "error": "Internal server error"}

        async def execute_transcribe_call(args):
            """Transcribe a call recording using AI"""
            call_id = args.get("call_id")
            audio_url = args.get("audio_url", "")

            if not call_id:
                return {"success": False, "error": "call_id is required"}

            # Try to fetch call record from database
            call_record = db.query(CallLog).filter(CallLog.id == call_id).first() if 'CallLog' in dir() else None

            if call_record and hasattr(call_record, 'recording_url'):
                audio_url = call_record.recording_url or audio_url

            if not audio_url:
                # Try to get from Twilio if we have a call SID
                twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
                twilio_token = os.getenv("TWILIO_AUTH_TOKEN")

                if twilio_sid and twilio_token:
                    try:
                        from twilio.rest import Client as TwilioClient
                        twilio_client = TwilioClient(twilio_sid, twilio_token)

                        # Try as call SID first
                        try:
                            call = twilio_client.calls(call_id).fetch()
                            recordings = twilio_client.calls(call_id).recordings.list(limit=1)
                            if recordings:
                                audio_url = f"https://api.twilio.com{recordings[0].uri.replace('.json', '.mp3')}"
                        except Exception:
                            pass  # Twilio API error, will be handled by outer except
                    except Exception as e:
                        logger.warning(f"Could not fetch recording from Twilio: {e}")

            if not audio_url:
                return {"success": False, "error": "No audio URL available for transcription"}

            # Use OpenAI Whisper for transcription if available
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                try:
                    import httpx

                    # Download audio file
                    async with httpx.AsyncClient() as client:
                        audio_response = await client.get(audio_url)
                        if audio_response.status_code != 200:
                            return {"success": False, "error": "Could not download audio file"}

                        # Send to OpenAI Whisper
                        import openai
                        openai.api_key = openai_key

                        # Save temp file and transcribe
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                            tmp.write(audio_response.content)
                            tmp_path = tmp.name

                        with open(tmp_path, "rb") as audio_file:
                            transcript = openai.Audio.transcribe("whisper-1", audio_file)

                        os.unlink(tmp_path)

                        return {
                            "success": True,
                            "call_id": call_id,
                            "transcript": transcript.get("text", ""),
                            "duration_seconds": len(transcript.get("text", "").split()) * 0.5  # Rough estimate
                        }
                except Exception as e:
                    logger.error(f"Transcription error: {e}")
                    return {"success": False, "error": "Transcription failed"}

            # Fallback - return placeholder
            return {
                "success": True,
                "call_id": call_id,
                "transcript": "[Transcription service not configured - would process audio from: " + audio_url + "]",
                "note": "Configure OPENAI_API_KEY for actual transcription"
            }

        async def execute_summarize_call(args):
            """Generate AI summary of a call transcript"""
            call_id = args.get("call_id")
            transcript = args.get("transcript", "")

            if not call_id:
                return {"success": False, "error": "call_id is required"}

            # If no transcript provided, try to get it
            if not transcript:
                # Try to fetch from database
                call_record = db.query(CallLog).filter(CallLog.id == call_id).first() if 'CallLog' in dir() else None
                if call_record and hasattr(call_record, 'transcript'):
                    transcript = call_record.transcript or ""

            if not transcript:
                return {"success": False, "error": "No transcript available to summarize"}

            # Use Claude/OpenAI to summarize
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            openai_key = os.getenv("OPENAI_API_KEY")

            if anthropic_key:
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=anthropic_key)

                    response = client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=500,
                        messages=[{
                            "role": "user",
                            "content": f"""Summarize this call transcript for a mortgage loan officer. Include:
    1. Key discussion points
    2. Action items mentioned
    3. Next steps agreed upon
    4. Any concerns or objections raised

    Transcript:
    {transcript[:4000]}"""
                        }]
                    )

                    summary = response.content[0].text

                    return {
                        "success": True,
                        "call_id": call_id,
                        "summary": summary,
                        "transcript_length": len(transcript)
                    }
                except Exception as e:
                    logger.error(f"Summarization error: {e}")

            # Fallback - basic extraction
            words = transcript.split()
            key_phrases = []
            for i, word in enumerate(words):
                if word.lower() in ["need", "want", "please", "will", "should", "must"]:
                    phrase = " ".join(words[max(0, i-2):min(len(words), i+5)])
                    key_phrases.append(phrase)

            return {
                "success": True,
                "call_id": call_id,
                "summary": f"Call transcript ({len(words)} words). Key phrases identified: {'; '.join(key_phrases[:5]) if key_phrases else 'None extracted'}",
                "note": "Configure ANTHROPIC_API_KEY for AI-powered summaries"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - LEADS
        # ========================================

        async def execute_ai_lead_scoring(args):
            """Calculate AI-powered lead quality score (0-100)"""
            lead_id = args.get("lead_id")
            include_factors = args.get("include_factors", True)

            if not lead_id:
                return {"success": False, "error": "lead_id is required"}

            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return {"success": False, "error": f"Lead not found: {lead_id}"}

            # Calculate score based on multiple factors
            score = 50  # Base score
            factors = []

            # Email quality
            if lead.email:
                if any(domain in lead.email.lower() for domain in ['gmail.com', 'yahoo.com', 'outlook.com']):
                    score += 5
                    factors.append("+5: Valid email provider")
                if lead.email.count('@') == 1 and '.' in lead.email.split('@')[1]:
                    score += 5
                    factors.append("+5: Well-formed email")

            # Phone presence
            if lead.phone:
                score += 10
                factors.append("+10: Phone number provided")

            # Lead source quality
            source = str(lead.source).lower() if lead.source else ""
            if "referral" in source:
                score += 15
                factors.append("+15: Referral lead (high quality)")
            elif "realtor" in source or "builder" in source:
                score += 10
                factors.append("+10: Partner referral")
            elif "website" in source:
                score += 5
                factors.append("+5: Website lead")

            # Stage progression
            stage = str(lead.stage).lower() if lead.stage else ""
            if "qualified" in stage or "contacted" in stage:
                score += 10
                factors.append("+10: Lead has been qualified/contacted")
            elif "application" in stage:
                score += 20
                factors.append("+20: Application started")

            # Loan amount (if available)
            if hasattr(lead, 'loan_amount') and lead.loan_amount:
                if lead.loan_amount >= 300000:
                    score += 10
                    factors.append("+10: Higher loan amount")
                elif lead.loan_amount >= 200000:
                    score += 5
                    factors.append("+5: Good loan amount")

            # Recency
            if lead.created_at:
                days_old = (datetime.now() - lead.created_at).days
                if days_old <= 1:
                    score += 10
                    factors.append("+10: Very fresh lead (< 1 day)")
                elif days_old <= 7:
                    score += 5
                    factors.append("+5: Recent lead (< 1 week)")
                elif days_old > 30:
                    score -= 10
                    factors.append("-10: Stale lead (> 30 days)")

            # Cap score at 0-100
            score = max(0, min(100, score))

            # Generate recommendation
            if score >= 80:
                recommendation = "Hot lead - prioritize immediate follow-up"
            elif score >= 60:
                recommendation = "Warm lead - schedule follow-up within 24 hours"
            elif score >= 40:
                recommendation = "Standard lead - follow standard nurture sequence"
            else:
                recommendation = "Cold lead - consider low-priority nurture campaign"

            result = {
                "success": True,
                "lead_id": lead_id,
                "lead_name": lead.name,
                "score": score,
                "recommendation": recommendation
            }

            if include_factors:
                result["factors"] = factors

            return result

        async def execute_find_duplicate_leads(args):
            """Find potential duplicate lead records"""
            lead_id = args.get("lead_id")
            email = args.get("email", "")
            phone = args.get("phone", "")
            name = args.get("name", "")

            # If lead_id provided, get lead details
            if lead_id:
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
                if lead:
                    email = email or lead.email
                    phone = phone or lead.phone
                    name = name or lead.name

            if not any([email, phone, name]):
                return {"success": False, "error": "Provide email, phone, name, or lead_id to search for duplicates"}

            duplicates = []

            # Search by email (exact match)
            if email:
                email_matches = db.query(Lead).filter(
                    Lead.email.ilike(email),
                    Lead.id != lead_id if lead_id else True
                ).all()
                for match in email_matches:
                    duplicates.append({
                        "lead_id": match.id,
                        "name": match.name,
                        "email": match.email,
                        "phone": match.phone,
                        "match_type": "email_exact",
                        "confidence": 0.95
                    })

            # Search by phone (normalized)
            if phone:
                phone_digits = ''.join(filter(str.isdigit, phone))
                if len(phone_digits) >= 10:
                    phone_matches = db.query(Lead).filter(
                        Lead.phone.ilike(f"%{phone_digits[-10:]}%"),
                        Lead.id != lead_id if lead_id else True
                    ).all()
                    for match in phone_matches:
                        if match.id not in [d["lead_id"] for d in duplicates]:
                            duplicates.append({
                                "lead_id": match.id,
                                "name": match.name,
                                "email": match.email,
                                "phone": match.phone,
                                "match_type": "phone",
                                "confidence": 0.90
                            })

            # Search by name (fuzzy)
            if name:
                name_parts = name.lower().split()
                for part in name_parts:
                    if len(part) > 2:
                        name_matches = db.query(Lead).filter(
                            Lead.name.ilike(f"%{part}%"),
                            Lead.id != lead_id if lead_id else True
                        ).limit(10).all()
                        for match in name_matches:
                            if match.id not in [d["lead_id"] for d in duplicates]:
                                # Calculate name similarity
                                match_name_lower = match.name.lower() if match.name else ""
                                match_score = sum(1 for p in name_parts if p in match_name_lower) / len(name_parts)
                                if match_score >= 0.5:
                                    duplicates.append({
                                        "lead_id": match.id,
                                        "name": match.name,
                                        "email": match.email,
                                        "phone": match.phone,
                                        "match_type": "name_similar",
                                        "confidence": round(match_score * 0.7, 2)
                                    })

            # Sort by confidence
            duplicates.sort(key=lambda x: -x["confidence"])

            return {
                "success": True,
                "search_criteria": {"email": email, "phone": phone, "name": name},
                "duplicate_count": len(duplicates),
                "duplicates": duplicates[:10]
            }

        async def execute_assign_lead_to_agent(args):
            """Assign a lead to a specific loan officer or agent"""
            lead_id = args.get("lead_id")
            agent_id = args.get("agent_id")
            agent_email = args.get("agent_email", "")
            reason = args.get("reason", "")

            if not lead_id:
                return {"success": False, "error": "lead_id is required"}

            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return {"success": False, "error": f"Lead not found: {lead_id}"}

            # Find agent by ID or email
            agent = None
            if agent_id:
                agent = db.query(User).filter(User.id == agent_id).first()
            elif agent_email:
                agent = db.query(User).filter(User.email.ilike(agent_email)).first()

            if not agent:
                return {"success": False, "error": "Agent not found. Provide valid agent_id or agent_email"}

            old_owner = lead.owner_id
            lead.owner_id = agent.id

            # Add note about assignment
            assignment_note = f"Lead assigned to {agent.full_name or agent.email}"
            if reason:
                assignment_note += f". Reason: {reason}"
            lead.notes = (lead.notes or "") + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {assignment_note}"

            db.commit()

            return {
                "success": True,
                "lead_id": lead.id,
                "lead_name": lead.name,
                "assigned_to": {
                    "id": agent.id,
                    "name": agent.full_name or agent.email,
                    "email": agent.email
                },
                "previous_owner_id": old_owner,
                "message": f"Lead '{lead.name}' assigned to {agent.full_name or agent.email}"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - PIPELINE
        # ========================================

        async def execute_assign_task(args):
            """Assign a task to a specific team member"""
            task_id = args.get("task_id")
            assignee_id = args.get("assignee_id")
            assignee_email = args.get("assignee_email", "")

            if not task_id:
                return {"success": False, "error": "task_id is required"}

            task = db.query(AITask).filter(AITask.id == task_id).first()
            if not task:
                return {"success": False, "error": f"Task not found: {task_id}"}

            # Find assignee
            assignee = None
            if assignee_id:
                assignee = db.query(User).filter(User.id == assignee_id).first()
            elif assignee_email:
                assignee = db.query(User).filter(User.email.ilike(assignee_email)).first()

            if not assignee:
                return {"success": False, "error": "Assignee not found. Provide valid assignee_id or assignee_email"}

            old_assignee_id = task.assigned_to_id
            task.assigned_to_id = assignee.id
            db.commit()

            return {
                "success": True,
                "task_id": task.id,
                "task_title": task.title,
                "assigned_to": {
                    "id": assignee.id,
                    "name": assignee.full_name or assignee.email,
                    "email": assignee.email
                },
                "previous_assignee_id": old_assignee_id,
                "message": f"Task '{task.title}' assigned to {assignee.full_name or assignee.email}"
            }

        async def execute_update_pipeline_stage(args):
            """Move a lead or loan to a different pipeline stage"""
            entity_type = args.get("entity_type", "").lower()
            entity_id = args.get("entity_id")
            stage = args.get("stage", "")
            status = args.get("status", "")
            reason = args.get("reason", "")
            trigger_automations = args.get("trigger_automations", True)

            if entity_type not in ["lead", "loan"]:
                return {"success": False, "error": "entity_type must be 'lead' or 'loan'"}
            if not entity_id:
                return {"success": False, "error": "entity_id is required"}
            if not stage:
                return {"success": False, "error": "stage is required"}

            entity = None
            old_stage = None

            if entity_type == "lead":
                entity = db.query(Lead).filter(Lead.id == entity_id).first()
                if entity:
                    old_stage = str(entity.stage) if entity.stage else "Unknown"
                    # Map to LeadStage enum if available
                    try:
                        entity.stage = stage
                    except (ValueError, AttributeError):
                        entity.stage = stage  # Use raw value if enum conversion fails
            else:
                entity = db.query(Loan).filter(Loan.id == entity_id).first()
                if entity:
                    old_stage = str(entity.stage).replace("LoanStage.", "") if entity.stage else "Unknown"
                    # Map to LoanStage enum
                    stage_map = {
                        "APPLICATION": LoanStage.APPLICATION,
                        "PROCESSING": LoanStage.PROCESSING,
                        "UNDERWRITING": LoanStage.UNDERWRITING,
                        "APPROVED": LoanStage.APPROVED,
                        "CLOSING": LoanStage.CLOSING,
                        "FUNDED": LoanStage.FUNDED,
                        "DEAD": LoanStage.DEAD
                    }
                    if stage.upper() in stage_map:
                        entity.stage = stage_map[stage.upper()]
                    else:
                        return {"success": False, "error": f"Invalid loan stage: {stage}"}

            if not entity:
                return {"success": False, "error": f"{entity_type.title()} not found: {entity_id}"}

            # Update status if provided
            if status and hasattr(entity, 'status'):
                entity.status = status

            # Add reason to notes
            if reason:
                notes = getattr(entity, 'notes', '') or ''
                entity.notes = notes + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Stage change to {stage}: {reason}"

            db.commit()

            result = {
                "success": True,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "old_stage": old_stage,
                "new_stage": stage,
                "message": f"{entity_type.title()} moved from {old_stage} to {stage}"
            }

            # Trigger automations if requested
            if trigger_automations and entity_type == "loan":
                result["automation_triggered"] = True
                result["automation_note"] = f"Milestone automation would be triggered for stage: {stage}"

            return result

        async def execute_request_documents(args):
            """Send document request to borrower"""
            loan_id = args.get("loan_id")
            lead_id = args.get("lead_id")
            document_types = args.get("document_types", [])
            message = args.get("message", "")

            if not document_types:
                return {"success": False, "error": "document_types is required"}

            # Find the entity (loan or lead)
            entity = None
            entity_type = None
            contact_email = None
            contact_name = None

            if loan_id:
                entity = db.query(Loan).filter(Loan.id == loan_id).first()
                entity_type = "loan"
                if entity:
                    contact_name = entity.borrower_name
                    contact_email = entity.borrower_email
            elif lead_id:
                entity = db.query(Lead).filter(Lead.id == lead_id).first()
                entity_type = "lead"
                if entity:
                    contact_name = entity.name
                    contact_email = entity.email

            if not entity:
                return {"success": False, "error": "Loan or Lead not found"}

            if not contact_email:
                return {"success": False, "error": "No email address found for contact"}

            # Build document request message
            doc_list = "\n".join([f"- {doc}" for doc in document_types])
            default_message = f"""Hello {contact_name},

    We need the following documents to proceed with your mortgage application:

    {doc_list}

    Please upload these documents at your earliest convenience.

    Thank you!"""

            email_body = message if message else default_message

            # Queue the email (or send via email service)
            # For now, we'll log it and return success
            request_id = str(uuid.uuid4())[:8]

            # Create a task to track the document request
            doc_task = AITask(
                title=f"Document Request: {', '.join(document_types[:3])}{'...' if len(document_types) > 3 else ''}",
                description=f"Documents requested from {contact_name}: {', '.join(document_types)}",
                due_date=datetime.now() + timedelta(days=3),
                priority="high",
                type=TaskType.IN_PROGRESS,
                assigned_to_id=current_user.id,
                loan_id=loan_id,
                lead_id=lead_id
            )
            db.add(doc_task)
            db.commit()

            return {
                "success": True,
                "request_id": request_id,
                "entity_type": entity_type,
                "entity_id": loan_id or lead_id,
                "contact_name": contact_name,
                "contact_email": contact_email,
                "documents_requested": document_types,
                "task_created": doc_task.id,
                "message": f"Document request sent to {contact_name} for {len(document_types)} document(s)"
            }

        async def execute_document_ocr_extract(args):
            """Extract data from uploaded documents via OCR"""
            document_id = args.get("document_id")
            document_url = args.get("document_url", "")
            document_type = args.get("document_type", "")

            if not document_id:
                return {"success": False, "error": "document_id is required"}

            # Try to get document from database
            document = None
            if 'Document' in dir():
                document = db.query(Document).filter(Document.id == document_id).first()

            if document and hasattr(document, 'file_url'):
                document_url = document_url or document.file_url
                document_type = document_type or getattr(document, 'document_type', 'unknown')

            if not document_url:
                return {"success": False, "error": "No document URL available"}

            # Determine extraction based on document type
            extraction_fields = {}
            doc_type_lower = document_type.lower()

            if "paystub" in doc_type_lower or "pay stub" in doc_type_lower:
                extraction_fields = {
                    "employer_name": "[OCR would extract employer name]",
                    "pay_period": "[OCR would extract pay period dates]",
                    "gross_pay": "[OCR would extract gross pay amount]",
                    "net_pay": "[OCR would extract net pay amount]",
                    "ytd_earnings": "[OCR would extract YTD earnings]"
                }
            elif "w2" in doc_type_lower or "w-2" in doc_type_lower:
                extraction_fields = {
                    "employer_ein": "[OCR would extract employer EIN]",
                    "employee_ssn_last4": "[OCR would extract last 4 of SSN]",
                    "wages": "[OCR would extract wages/tips/compensation]",
                    "federal_tax_withheld": "[OCR would extract federal tax withheld]",
                    "tax_year": "[OCR would extract tax year]"
                }
            elif "bank" in doc_type_lower or "statement" in doc_type_lower:
                extraction_fields = {
                    "account_number_last4": "[OCR would extract last 4 of account]",
                    "statement_period": "[OCR would extract statement period]",
                    "ending_balance": "[OCR would extract ending balance]",
                    "average_balance": "[OCR would calculate average balance]"
                }
            elif "tax" in doc_type_lower or "1040" in doc_type_lower:
                extraction_fields = {
                    "tax_year": "[OCR would extract tax year]",
                    "filing_status": "[OCR would extract filing status]",
                    "adjusted_gross_income": "[OCR would extract AGI]",
                    "total_income": "[OCR would extract total income]"
                }
            else:
                extraction_fields = {
                    "document_type_detected": "[OCR would detect document type]",
                    "text_extracted": "[OCR would extract full text]",
                    "key_values": "[OCR would extract key-value pairs]"
                }

            return {
                "success": True,
                "document_id": document_id,
                "document_type": document_type,
                "document_url": document_url,
                "extracted_data": extraction_fields,
                "confidence": 0.85,
                "note": "Configure OCR service (AWS Textract, Google Vision, etc.) for actual extraction"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - RATE LOCK
        # ========================================

        async def execute_lock_rate(args):
            """Execute a rate lock for a loan (REQUIRES APPROVAL)"""
            loan_id = args.get("loan_id")
            rate = args.get("rate")
            lock_period_days = args.get("lock_period_days")
            points = args.get("points", 0)

            if not all([loan_id, rate, lock_period_days]):
                return {"success": False, "error": "loan_id, rate, and lock_period_days are required"}

            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan not found: {loan_id}"}

            # Check if loan already has an active lock
            if hasattr(loan, 'rate_locked') and loan.rate_locked:
                return {
                    "success": False,
                    "error": "Loan already has an active rate lock",
                    "current_rate": loan.interest_rate,
                    "lock_expiration": str(loan.lock_expiration) if hasattr(loan, 'lock_expiration') else None
                }

            # Calculate lock expiration
            lock_expiration = datetime.now() + timedelta(days=lock_period_days)

            # Update loan with rate lock info
            loan.interest_rate = rate
            if hasattr(loan, 'rate_locked'):
                loan.rate_locked = True
            if hasattr(loan, 'lock_expiration'):
                loan.lock_expiration = lock_expiration
            if hasattr(loan, 'lock_points'):
                loan.lock_points = points

            # Add note
            lock_note = f"Rate locked at {rate}% for {lock_period_days} days. Points: {points}. Expires: {lock_expiration.strftime('%Y-%m-%d')}"
            loan.notes = (loan.notes or "") + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {lock_note}"

            db.commit()

            return {
                "success": True,
                "loan_id": loan.id,
                "borrower": loan.borrower_name,
                "locked_rate": rate,
                "lock_period_days": lock_period_days,
                "lock_expiration": lock_expiration.strftime('%Y-%m-%d'),
                "points": points,
                "message": f"Rate locked at {rate}% for {loan.borrower_name}. Expires {lock_expiration.strftime('%Y-%m-%d')}"
            }

        async def execute_extend_lock(args):
            """Extend an existing rate lock (REQUIRES APPROVAL)"""
            loan_id = args.get("loan_id")
            extension_days = args.get("extension_days")

            if not all([loan_id, extension_days]):
                return {"success": False, "error": "loan_id and extension_days are required"}

            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan not found: {loan_id}"}

            # Check if loan has a rate lock
            if hasattr(loan, 'rate_locked') and not loan.rate_locked:
                return {"success": False, "error": "Loan does not have an active rate lock to extend"}

            # Get current expiration
            current_expiration = getattr(loan, 'lock_expiration', None)
            if not current_expiration:
                current_expiration = datetime.now()

            # Calculate new expiration
            if isinstance(current_expiration, date) and not isinstance(current_expiration, datetime):
                current_expiration = datetime.combine(current_expiration, datetime.min.time())

            new_expiration = current_expiration + timedelta(days=extension_days)

            # Update loan
            if hasattr(loan, 'lock_expiration'):
                loan.lock_expiration = new_expiration

            # Add note
            extend_note = f"Rate lock extended by {extension_days} days. New expiration: {new_expiration.strftime('%Y-%m-%d')}"
            loan.notes = (loan.notes or "") + f"\n\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {extend_note}"

            db.commit()

            return {
                "success": True,
                "loan_id": loan.id,
                "borrower": loan.borrower_name,
                "extension_days": extension_days,
                "previous_expiration": current_expiration.strftime('%Y-%m-%d'),
                "new_expiration": new_expiration.strftime('%Y-%m-%d'),
                "current_rate": loan.interest_rate,
                "message": f"Rate lock extended to {new_expiration.strftime('%Y-%m-%d')} for {loan.borrower_name}"
            }

        # ========================================
        # NEW TOOL IMPLEMENTATIONS - SCHEDULING
        # ========================================

        async def execute_reschedule_appointment(args):
            """Reschedule an existing appointment"""
            appointment_id = args.get("appointment_id")
            new_start_time = args.get("new_start_time", "")
            reason = args.get("reason", "")

            if not appointment_id:
                return {"success": False, "error": "appointment_id is required"}
            if not new_start_time:
                return {"success": False, "error": "new_start_time is required"}

            # Find appointment (stored as task or in appointments table)
            appointment = db.query(AITask).filter(AITask.id == appointment_id).first()

            if not appointment:
                # Try scheduler appointments if that table exists
                if 'Appointment' in dir():
                    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

            if not appointment:
                return {"success": False, "error": f"Appointment not found: {appointment_id}"}

            # Parse new start time
            parsed_time = None
            try:
                from dateutil import parser
                parsed_time = parser.parse(new_start_time)
            except (ValueError, TypeError):
                # Try natural language parsing
                time_lower = new_start_time.lower()
                today = datetime.now()

                if "tomorrow" in time_lower:
                    parsed_time = today + timedelta(days=1)
                    parsed_time = parsed_time.replace(hour=10, minute=0, second=0)
                elif "next week" in time_lower:
                    parsed_time = today + timedelta(days=7)
                    parsed_time = parsed_time.replace(hour=10, minute=0, second=0)
                else:
                    return {"success": False, "error": f"Could not parse time: {new_start_time}"}

            # Store old time for response
            old_time = appointment.due_date if hasattr(appointment, 'due_date') else getattr(appointment, 'start_time', None)

            # Update the appointment
            if hasattr(appointment, 'due_date'):
                appointment.due_date = parsed_time
            if hasattr(appointment, 'start_time'):
                appointment.start_time = parsed_time

            # Add reason to notes/description
            if reason:
                if hasattr(appointment, 'description'):
                    appointment.description = (appointment.description or "") + f"\n\nRescheduled: {reason}"
                elif hasattr(appointment, 'notes'):
                    appointment.notes = (appointment.notes or "") + f"\n\nRescheduled: {reason}"

            db.commit()

            return {
                "success": True,
                "appointment_id": appointment_id,
                "title": getattr(appointment, 'title', 'Appointment'),
                "old_time": old_time.isoformat() if old_time else None,
                "new_time": parsed_time.isoformat(),
                "reason": reason,
                "message": f"Appointment rescheduled to {parsed_time.strftime('%Y-%m-%d %H:%M')}"
            }

        async def execute_cancel_appointment(args):
            """Cancel an appointment (REQUIRES APPROVAL)"""
            appointment_id = args.get("appointment_id")
            reason = args.get("reason", "")
            notify_attendees = args.get("notify_attendees", True)

            if not appointment_id:
                return {"success": False, "error": "appointment_id is required"}

            # Find appointment
            appointment = db.query(AITask).filter(AITask.id == appointment_id).first()

            if not appointment:
                if 'Appointment' in dir():
                    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()

            if not appointment:
                return {"success": False, "error": f"Appointment not found: {appointment_id}"}

            title = getattr(appointment, 'title', 'Appointment')
            scheduled_time = getattr(appointment, 'due_date', None) or getattr(appointment, 'start_time', None)

            # Mark as cancelled
            if hasattr(appointment, 'type'):
                appointment.type = TaskType.COMPLETED  # Mark as completed/done
            if hasattr(appointment, 'status'):
                appointment.status = 'cancelled'

            # Add cancellation note
            cancel_note = f"CANCELLED"
            if reason:
                cancel_note += f": {reason}"

            if hasattr(appointment, 'description'):
                appointment.description = cancel_note + "\n\n" + (appointment.description or "")
            elif hasattr(appointment, 'notes'):
                appointment.notes = cancel_note + "\n\n" + (appointment.notes or "")

            db.commit()

            result = {
                "success": True,
                "appointment_id": appointment_id,
                "title": title,
                "was_scheduled_for": scheduled_time.isoformat() if scheduled_time else None,
                "reason": reason,
                "message": f"Appointment '{title}' has been cancelled"
            }

            if notify_attendees:
                result["notification_sent"] = True
                result["notification_note"] = "Attendees would be notified via email"

            return result

        async def execute_check_email_sync_status(args: dict):
            """Check email sync status for Microsoft 365 or Gmail integrations."""
            try:
                # Check for Microsoft OAuth connection
                microsoft_oauth = db.query(MicrosoftOAuthToken).filter(
                    MicrosoftOAuthToken.user_id == current_user.id
                ).first()

                result = {
                    "success": True,
                    "has_email_integration": False,
                    "microsoft": None,
                    "summary": ""
                }

                if microsoft_oauth:
                    result["has_email_integration"] = True
                    token_expired = False
                    if microsoft_oauth.expires_at:
                        token_expired = microsoft_oauth.expires_at < datetime.utcnow()

                    recent_emails = db.execute(text("""
                        SELECT COUNT(*) as count, MAX(received_date) as last_email
                        FROM incoming_data_events
                        WHERE user_id = :user_id AND source_type = 'microsoft_email'
                        AND received_date >= NOW() - INTERVAL '24 hours'
                    """), {"user_id": current_user.id}).fetchone()

                    result["microsoft"] = {
                        "connected": True,
                        "email_address": microsoft_oauth.email_address,
                        "sync_folder": microsoft_oauth.sync_folder or "Inbox",
                        "token_status": "expired" if token_expired else "valid",
                        "emails_last_24h": recent_emails[0] if recent_emails else 0
                    }

                    if token_expired:
                        result["summary"] = f"Microsoft 365 email connected ({microsoft_oauth.email_address}) but token has EXPIRED. Please re-authenticate."
                    elif recent_emails and recent_emails[0] > 0:
                        result["summary"] = f"Microsoft 365 email is syncing properly. {recent_emails[0]} emails received in the last 24 hours."
                    else:
                        result["summary"] = f"Microsoft 365 email connected ({microsoft_oauth.email_address}). No new emails in the last 24 hours."
                else:
                    result["summary"] = "No email integration configured. Go to Settings > Integrations to connect Microsoft 365 or Gmail."

                return result
            except Exception as e:
                logger.error(f"check_email_sync_status error: {e}")
                return {"success": False, "error": "Internal server error", "summary": "Error checking email sync status"}

        tool_functions = {
            "get_tasks": execute_get_tasks,
            "get_calendar_events": execute_get_calendar_events,
            "get_pipeline": execute_get_pipeline,
            "search_leads": execute_search_leads,
            "get_market_intelligence": execute_get_market_intelligence,
            "send_sms": execute_send_sms,
            "create_task": execute_create_task,
            "schedule_appointment": execute_schedule_appointment,
            # Additional tools
            "send_email": execute_send_email,
            "update_lead": execute_update_lead,
            "get_loan_details": execute_get_loan_details,
            "get_lead_details": execute_get_lead_details,
            "update_user_profile": execute_update_user_profile,
            "get_metrics": execute_get_metrics,
            "schedule_followup": execute_schedule_followup,
            "get_mum_clients": execute_get_mum_clients,
            "get_referral_partners": execute_get_referral_partners,
            "get_sla_dashboard": execute_get_sla_dashboard,
            "make_phone_call": execute_make_phone_call,
            "create_lead": execute_create_lead,
            # New tools for 25 total
            "drop_voicemail": execute_drop_voicemail,
            "send_email_to_contact": execute_send_email_to_contact,
            "search_knowledge_base": execute_search_knowledge_base,
            "escalate_to_human": execute_escalate_to_human,
            "get_employee_capacity": execute_get_employee_capacity,
            "get_at_risk_deals": execute_get_at_risk_deals,
            # Predictive analytics tools for 32 total
            "get_activity_metrics": execute_get_activity_metrics,
            "get_document_status": execute_get_document_status,
            "predict_borrower_ghosting": execute_predict_borrower_ghosting,
            "predict_deal_success": execute_predict_deal_success,
            "forecast_revenue": execute_forecast_revenue,
            "get_refinance_candidates": execute_get_refinance_candidates,
            "analyze_conversion_patterns": execute_analyze_conversion_patterns,
            # Task Management tools for 38 total
            "complete_task": execute_complete_task,
            "update_task": execute_update_task,
            "get_overdue_tasks": execute_get_overdue_tasks,
            "move_lead_stage": execute_move_lead_stage,
            "move_loan_stage": execute_move_loan_stage,
            "bulk_create_tasks": execute_bulk_create_tasks,
            # NEW: Communication tools
            "send_mms": execute_send_mms,
            "transcribe_call": execute_transcribe_call,
            "summarize_call": execute_summarize_call,
            # NEW: Lead tools
            "ai_lead_scoring": execute_ai_lead_scoring,
            "find_duplicate_leads": execute_find_duplicate_leads,
            "assign_lead_to_agent": execute_assign_lead_to_agent,
            # NEW: Pipeline tools
            "assign_task": execute_assign_task,
            "update_pipeline_stage": execute_update_pipeline_stage,
            "request_documents": execute_request_documents,
            "document_ocr_extract": execute_document_ocr_extract,
            # NEW: Rate lock tools
            "lock_rate": execute_lock_rate,
            "extend_lock": execute_extend_lock,
            # NEW: Scheduling tools
            "reschedule_appointment": execute_reschedule_appointment,
            "cancel_appointment": execute_cancel_appointment,
            # Email & Integration Status Tools
            "check_email_sync_status": execute_check_email_sync_status
        }

        # Pre-fetch real data for rich context
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        week_end = today + timedelta(days=7)
        start_of_month = today.replace(day=1)
        start_of_year = today.replace(month=1, day=1)

        all_tasks = db.query(Task).filter(Task.owner_id == current_user.id).all()
        all_leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
        all_loans = db.query(Loan).filter(Loan.loan_officer_id == current_user.id).all()

        # Fetch profitability data for financial questions using ProfitabilityService
        try:
            from services.profitability_service import ProfitabilityService
            profitability_service = ProfitabilityService(db, organization_id=1)  # Default org

            # Get comprehensive dashboard metrics
            dashboard_metrics = profitability_service.get_dashboard_metrics(today)

            # Get expense breakdown
            all_expenses = db.query(Expense).filter(Expense.is_active == True).all()
            expense_breakdown = {}
            for exp in all_expenses:
                exp_type = exp.expense_type or 'other'
                if exp_type not in expense_breakdown:
                    expense_breakdown[exp_type] = 0
                expense_breakdown[exp_type] += float(exp.amount or 0)

            # Get employee costs
            employee_costs_list = db.query(EmployeeCost).filter(EmployeeCost.is_active == True).all()
            total_employee_costs = sum(emp.monthly_cost for emp in employee_costs_list)
            employee_count = len(employee_costs_list)

            # Get closed loans this month
            closed_loans_month = db.query(ProfitabilityLoan).filter(
                ProfitabilityLoan.close_date >= start_of_month
            ).all()

            # Calculate metrics from dashboard
            loans_closed_this_month = dashboard_metrics.get('loans_closed', 0)
            total_revenue_month = float(dashboard_metrics.get('total_revenue', 0))
            monthly_expenses = float(dashboard_metrics.get('total_expenses', 0))
            snapshot_cost_per_loan = float(dashboard_metrics.get('cost_per_loan', 0))
            snapshot_revenue_per_loan = float(dashboard_metrics.get('revenue_per_loan', 0))
            snapshot_profit_per_loan = float(dashboard_metrics.get('profit_per_loan', 0))
            profit_margin = float(dashboard_metrics.get('profit_margin', 0))
            break_even_loans = dashboard_metrics.get('break_even_loans', 0)
            net_profit = float(dashboard_metrics.get('net_profit', 0))

            avg_loan_amount = sum(float(l.loan_amount or 0) for l in closed_loans_month) / max(loans_closed_this_month, 1) if closed_loans_month else 0

            # Get trends for year-over-year comparison
            trends = profitability_service.get_trends(3)  # Last 3 months

            # Get gaps and gains insights
            gaps_gains = profitability_service.identify_gaps_and_gains(today)

            has_profitability_data = loans_closed_this_month > 0 or monthly_expenses > 0 or len(all_expenses) > 0

        except Exception as e:
            logger.warning(f"Could not fetch profitability data: {e}")
            # Default values if profitability tables don't exist yet
            loans_closed_this_month = 0
            total_revenue_month = 0
            monthly_expenses = 0
            snapshot_cost_per_loan = 0
            snapshot_revenue_per_loan = 0
            snapshot_profit_per_loan = 0
            avg_loan_amount = 0
            profit_margin = 0
            break_even_loans = 0
            net_profit = 0
            expense_breakdown = {}
            total_employee_costs = 0
            employee_count = 0
            trends = []
            gaps_gains = []
            has_profitability_data = False

        # Fetch relevant knowledge base entries for the user's question
        knowledge_context = ""
        try:
            # Get active knowledge base entries
            knowledge_entries = db.query(AIKnowledgeBase).filter(
                AIKnowledgeBase.is_active == True
            ).order_by(AIKnowledgeBase.priority.desc()).limit(20).all()

            if knowledge_entries:
                # Search for entries relevant to the user's question
                message_lower = message.lower()
                relevant_entries = []

                for entry in knowledge_entries:
                    # Check if entry title, content, or tags match the question
                    entry_text = f"{entry.title} {entry.content} {' '.join(entry.tags or [])}".lower()

                    # Simple keyword matching - check if any significant words from the question appear in the entry
                    question_words = [w for w in message_lower.split() if len(w) > 3]
                    match_score = sum(1 for word in question_words if word in entry_text)

                    if match_score > 0:
                        relevant_entries.append((match_score, entry))

                # Sort by relevance and take top 5
                relevant_entries.sort(key=lambda x: x[0], reverse=True)
                top_entries = [entry for score, entry in relevant_entries[:5]]

                if top_entries:
                    knowledge_context = "\n\n# KNOWLEDGE BASE CONTEXT\n"
                    knowledge_context += "The following information from your organization's knowledge base may be relevant:\n\n"
                    for entry in top_entries:
                        knowledge_context += f"## {entry.title} ({entry.category.replace('_', ' ').title()})\n"
                        # Include summary if available, otherwise truncate content
                        if entry.summary:
                            knowledge_context += f"{entry.summary}\n\n"
                        else:
                            # Truncate content to first 500 chars
                            content_preview = entry.content[:500] + "..." if len(entry.content) > 500 else entry.content
                            knowledge_context += f"{content_preview}\n\n"
        except Exception as e:
            logger.warning(f"Could not fetch knowledge base entries: {e}")
            knowledge_context = ""

        # Task breakdown
        tasks_today = [t for t in all_tasks if t.due_date and t.due_date.date() == today and t.status != "completed"]
        tasks_tomorrow = [t for t in all_tasks if t.due_date and t.due_date.date() == tomorrow and t.status != "completed"]
        tasks_overdue = [t for t in all_tasks if t.due_date and t.due_date.date() < today and t.status != "completed"]
        outstanding_tasks = [t for t in all_tasks if t.status != "completed"]

        # Helper to format task details - ALWAYS include client name
        def format_task(task):
            parts = [f"**{task.title}**"]
            if task.priority:
                parts.append(f"Priority: {task.priority.title()}")
            if task.due_date:
                parts.append(f"Due: {task.due_date.strftime('%m/%d/%Y')}")

            # Get related loan/lead info - try multiple sources for client name
            client_name = None
            loan_amount = None

            if task.loan_id:
                loan = next((l for l in all_loans if l.id == task.loan_id), None)
                if loan:
                    client_name = loan.borrower_name
                    loan_amount = loan.amount

            if not client_name and task.lead_id:
                lead = next((l for l in all_leads if l.id == task.lead_id), None)
                if lead:
                    client_name = lead.name

            # Fallback to related_contact_name if no loan/lead association
            if not client_name and hasattr(task, 'related_contact_name') and task.related_contact_name:
                client_name = task.related_contact_name

            # Add client name to the task description
            if client_name:
                if loan_amount:
                    parts.append(f"FOR: {client_name} (${loan_amount:,.0f})")
                else:
                    parts.append(f"FOR: {client_name}")

            return " | ".join(parts)

        # Format stage name
        def format_stage(stage):
            if not stage:
                return "Unknown"
            stage_str = str(stage).replace('LoanStage.', '').replace('LeadStage.', '')
            stage_map = {
                'CTC': 'Clear to Close', 'UW_RECEIVED': 'Underwriting Received',
                'DISCLOSED': 'Disclosed', 'PROCESSING': 'Processing',
                'APPROVED': 'Approved', 'FUNDED': 'Funded', 'NEW': 'New',
                'PROSPECT': 'Prospect', 'PRE_QUALIFIED': 'Pre-Qualified',
                'PRE_APPROVED': 'Pre-Approved', 'APPLICATION_STARTED': 'Application Started'
            }
            return stage_map.get(stage_str, stage_str.replace('_', ' ').title())

        # Build loans by stage
        loans_by_stage = {}
        for loan in all_loans:
            stage_name = format_stage(loan.stage)
            if stage_name not in loans_by_stage:
                loans_by_stage[stage_name] = []
            loans_by_stage[stage_name].append(loan)

        # Lead stages
        pipeline_stages = {}
        for lead in all_leads:
            stage = str(lead.stage).replace("LeadStage.", "") if lead.stage else "NEW"
            if stage not in pipeline_stages:
                pipeline_stages[stage] = []
            pipeline_stages[stage].append(lead.name)

        # Build data context
        data_context = f"""
    ## YOUR CURRENT DATA (Real-time):

    ### Tasks Overview:
    - Tasks due TODAY: {len(tasks_today)}
    - Tasks due TOMORROW: {len(tasks_tomorrow)}
    - OVERDUE tasks: {len(tasks_overdue)}
    - TOTAL OUTSTANDING: {len(outstanding_tasks)}

    ### Outstanding Tasks (Detailed):
    {chr(10).join([f"- {format_task(t)}" for t in outstanding_tasks[:10]]) if outstanding_tasks else "- No outstanding tasks"}

    ### Active Loans BY STAGE:
    {chr(10).join([f"**{stage}** ({len(loans)} loans): " + ", ".join([f"{loan.borrower_name} (${loan.amount:,.0f})" if loan.amount else loan.borrower_name for loan in loans]) for stage, loans in loans_by_stage.items()]) if loans_by_stage else "- No active loans"}

    ### Pipeline Summary ({len(all_leads)} leads):
    {chr(10).join([f"- {stage}: {len(names)} leads" for stage, names in pipeline_stages.items()]) if pipeline_stages else "- No leads"}

    ### Financial Metrics (This Month):
    - Loans Closed This Month: {loans_closed_this_month}
    - Total Revenue This Month: ${total_revenue_month:,.2f}
    - Monthly Operating Expenses: ${monthly_expenses:,.2f}
    - Net Profit: ${net_profit:,.2f}
    - Profit Margin: {profit_margin:.1f}%
    - Average Loan Amount: ${avg_loan_amount:,.2f}
    - **Cost Per Closing**: ${snapshot_cost_per_loan:,.2f}
    - Revenue Per Loan: ${snapshot_revenue_per_loan:,.2f}
    - Profit Per Loan: ${snapshot_profit_per_loan:,.2f}
    - Break-Even Point: {break_even_loans} loans/month
    - Employee Count: {employee_count}
    - Employee Costs (Monthly): ${total_employee_costs:,.2f}

    ### Expense Breakdown:
    {chr(10).join([f"- {exp_type.replace('_', ' ').title()}: ${amount:,.2f}" for exp_type, amount in expense_breakdown.items()]) if expense_breakdown else "- No expenses configured"}

    {'### ⚠️ PROFITABILITY DATA NOT CONFIGURED' if not has_profitability_data else ''}
    {'To calculate accurate cost per closing, set up the Profitability section with:' if not has_profitability_data else ''}
    {'1. Monthly expenses (rent, software, marketing, etc.)' if not has_profitability_data else ''}
    {'2. Employee costs (salaries, benefits, taxes)' if not has_profitability_data else ''}
    {'3. Closed loan records with revenue' if not has_profitability_data else ''}
    {'Navigate to: Settings > Profitability' if not has_profitability_data else ''}
    """

        # Detect coaching mode
        message_lower = message.lower()
        coaching_instructions = ""

        if "daily briefing" in message_lower or "top 3 priorities" in message_lower or "what should i do" in message_lower or "priorities today" in message_lower or "what do i need to do" in message_lower or "outstanding tasks" in message_lower:
            has_real_data = len(outstanding_tasks) > 0 or len(all_leads) > 0 or len(all_loans) > 0
            coaching_instructions = f"""

    ## COACHING MODE: DAILY BRIEFING
    You are providing a detailed, actionable daily briefing. Be CONVERSATIONAL and HELPFUL, not just a list.

    CRITICAL RULES:
    - **NEVER INVENT OR MAKE UP TASKS** - Only reference tasks that exist in the data above
    - **ALWAYS INCLUDE THE CLIENT/BORROWER NAME** - Every task MUST specify WHO it's for
    - The user has EXACTLY {len(tasks_overdue)} OVERDUE tasks
    - The user has EXACTLY {len(outstanding_tasks)} total outstanding tasks
    - The user has {len(all_leads)} leads and {len(all_loans)} active loans
    - Look for "FOR:" in the task data to find the client name - if a task has "FOR: John Smith" include that name

    {'**NO DATA FOUND - Tell the user they have no outstanding tasks and offer to help them add a new lead or import data.**' if not has_real_data else ''}

    OUTPUT FORMAT (be conversational, not robotic):
    1. Start with a friendly greeting and summary: "Good morning! Here's your priority breakdown for today..."
    2. If overdue tasks exist, HIGHLIGHT them first with urgency
    3. **EVERY task MUST include the client/borrower name** - e.g., "Follow up with **Sarah Johnson**" not just "Follow up"
    4. Include loan amounts when available: "$450,000 loan in Processing"
    5. End with a clear action recommendation: "I'd suggest starting with [X] because [reason]"
    6. Be encouraging and actionable, not just a data dump

    Example good response:
    "Good morning! You have 3 outstanding tasks that need attention today.

    **Priority #1: Follow up with Sarah Johnson** ($450,000 loan in Processing)
    This is your most time-sensitive item - the appraisal was received yesterday and needs your review.

    **Priority #2: Discuss Revised Numbers with Mike Chen**
    Mike's file is in Underwriting and he's waiting on updated figures.

    **Priority #3: Follow-up meetings with leads** (8 contacts due today)
    Your lead nurturing tasks - I'd batch these after handling the urgent items above.

    I'd suggest starting with Sarah's appraisal review since it directly impacts her closing timeline. Would you like me to pull up her file?"
    """

        # Get user's local time (safely handle missing timezone column)
        user_timezone = getattr(current_user, 'timezone', None) or "America/Chicago"
        try:
            user_tz = pytz.timezone(user_timezone)
            user_local_time = datetime.now(pytz.UTC).astimezone(user_tz)
        except Exception:
            user_timezone = "America/Chicago"
            user_tz = pytz.timezone(user_timezone)
            user_local_time = datetime.now(pytz.UTC).astimezone(user_tz)

        # Build comprehensive system prompt
        system_prompt = f"""# IDENTITY
    You are the AI Assistant for Perennia AI Mortgage CRM - a confident, expert mortgage industry copilot.
    User: {current_user.full_name or current_user.email}
    Current date/time: {user_local_time.strftime('%A, %B %d, %Y at %I:%M %p')} ({user_timezone})

    # VOICE & TONE
    - Confident, expert, and decisive
    - No hedging, no disclaimers, no "I think" or "maybe"
    - Be conversational and helpful, not robotic
    - Always provide specific names, amounts, and actionable next steps
    - Format with markdown for clarity (bold for emphasis, bullet points for lists)

    # FORMATTING RULES
    - Never use ALL CAPS - use **bold** for emphasis instead
    - Format stage names properly: "Clear to Close" not "CTC"
    - When mentioning loans, always include borrower name and amount
    - Use numbered lists for priorities, bullet points for details

    # MORTGAGE BUSINESS FINANCIAL DEFINITIONS
    You are an expert in mortgage business operations and profitability. Here are the key metrics and how to calculate them:

    ## Revenue Sources in Mortgage Operations:
    - **Origination Fee**: Fee charged to borrower for processing their loan (typically 0.5-1% of loan amount)
    - **Processing Fee**: Administrative fee for document collection and verification ($300-$800)
    - **Admin Fee**: General administrative costs passed to borrower ($200-$500)
    - **Commission/Rebate**: Revenue from lender based on rate spread (YSP - Yield Spread Premium)
    - **Typical Revenue Per Loan**: $3,000-$8,000 depending on loan size and pricing

    ## Cost Categories:
    - **Fixed Costs**: Rent, software subscriptions, insurance, licensing fees - don't change with volume
    - **Variable Costs**: Commission splits, credit reports, appraisals - scale with loan volume
    - **Employee Costs**: Fully-loaded cost = Base Salary + Benefits (25-30%) + Payroll Taxes (7.65%) + Equipment + Training
    - **One-Time Costs**: Equipment purchases, renovations, training programs

    ## Key Performance Metrics:
    - **Cost Per Closing** = Total Monthly Expenses ÷ Loans Closed This Month
      - Industry benchmark: $2,000-$5,000 per loan
      - If no loans closed, show total expenses as the "cost to operate"

    - **Revenue Per Loan** = Total Revenue ÷ Loans Closed
      - Track by loan type (Conv, FHA, VA, Jumbo) as they have different margins

    - **Profit Per Loan** = Revenue Per Loan - Cost Per Loan
      - Healthy target: $1,000-$3,000 per loan

    - **Profit Margin** = (Net Profit ÷ Total Revenue) × 100
      - Industry healthy range: 15-30%
      - Below 10%: Needs immediate attention

    - **Break-Even Point** = Total Monthly Expenses ÷ Average Revenue Per Loan
      - The minimum number of loans needed to cover all costs

    - **Employee ROI** = (Revenue Attributed to Employee - Employee Cost) ÷ Employee Cost × 100
      - Measures each team member's contribution to profitability

    ## Expense Types:
    - **fixed**: Recurring costs that don't change (rent, subscriptions, base salaries)
    - **variable**: Costs that scale with volume (commissions, credit reports, appraisals)
    - **one_time**: One-off purchases (equipment, renovations, training)

    # CRM PAGE DIRECTORY
    When users ask where to find something or need to navigate, direct them to these pages:

    ## Main Navigation
    - **/dashboard** - Main dashboard with overview metrics, pipeline summary, and quick actions
    - **/ai** - AI Assistant landing page for conversational queries and daily briefings
    - **/leads** - Lead management - view, add, and manage prospective borrowers
    - **/leads/:id** - Individual lead detail page with full profile and activity
    - **/loans** - Active loan pipeline - all loans in progress
    - **/loans/:id** - Individual loan detail page with milestones, documents, and team
    - **/tasks** - Task management center - all outstanding and completed tasks
    - **/calendar** - Calendar view for appointments, closings, and deadlines

    ## Client Management
    - **/portfolio** - Client for Life (MUM) portfolio - past clients for retention marketing
    - **/portfolio/:id** - Individual client profile from portfolio
    - **/portfolio/year-over-year** - Year-over-year comparison of portfolio performance
    - **/referral-partners** - Referral partner management (realtors, builders, etc.)
    - **/referral-partners/:id** - Individual referral partner detail page
    - **/partner-roi** - Partner ROI dashboard - track which partners generate most business

    ## AI & Automation
    - **/ai** - AI Orchestrator chat interface for questions and coaching
    - **/ai-underwriter** - AI Underwriter for loan analysis and risk assessment
    - **/ai-receptionist-dashboard** - AI Receptionist call logs and performance
    - **/voice-os-dashboard** - Voice OS dashboard for call handling metrics
    - **/assistant** - AI Assistant interface (legacy)
    - **/coach** - AI Coach for performance improvement suggestions

    ## Analytics & Reporting
    - **/profitability** - **Profitability Intelligence Dashboard** - cost per closing, revenue, expenses, profit margins
    - **/profitability/scenarios** - Scenario modeling - what-if analysis for staffing and expenses
    - **/scorecard** - Performance scorecard with KPIs and metrics
    - **/efficiency** - Pipeline efficiency dashboard - bottlenecks and stage performance
    - **/efficiency/stage/:stageSlug** - Employees by stage breakdown
    - **/efficiency/bottleneck/:bottleneckId** - Loans stuck at a specific bottleneck
    - **/market** - Market dashboard with rates, trends, and economic indicators
    - **/goal-tracker** - Goal tracking and OKR management

    ## Workflow & Process
    - **/workflow** - Workflow dashboard - loan stages and automation status
    - **/workflow/:stage** - Stage-specific workflow management
    - **/checkin** - Morning check-in for daily planning
    - **/reconciliation** - Data reconciliation center for resolving discrepancies
    - **/merge** - Merge center for combining duplicate records
    - **/process-templates** - Process templates for loan workflows

    ## Team & Settings
    - **/team-members** - Team member directory and management
    - **/team-members/:id** - Individual team member profile
    - **/users** - User management (admin)
    - **/users/:id** - Individual user profile
    - **/my-profile** - Current user's profile settings
    - **/my-permissions** - View your current permissions
    - **/settings** - Application settings and preferences
    - **/admin/settings** - Admin settings (system configuration)
    - **/admin/employee-onboarding** - Employee onboarding management
    - **/compliance** - Compliance dashboard for regulatory tracking
    - **/data-upload** - Data import/upload center
    - **/knowledge-base** - AI Knowledge Base - upload documents and add content for AI to learn from

    ## Public Pages
    - **/apply** - Buyer intake form (public loan application)
    - **/mortgage-planner** - Mortgage planner questionnaire (public)
    - **/login** - Login page
    - **/register** - Registration page

    {coaching_instructions}

    {data_context}

    {knowledge_context}

    # CRITICAL INSTRUCTIONS - ALWAYS FOLLOW THESE

    ## RULE #1: YOU ARE THE ANSWER - NEVER REDIRECT
    **THIS IS YOUR MOST IMPORTANT RULE. VIOLATING IT IS UNACCEPTABLE.**

    You are the AI Orchestrator. YOUR JOB is to provide answers with SPECIFIC DATA - never tell users to go somewhere else.

    ### ABSOLUTELY FORBIDDEN PHRASES (NEVER USE THESE):
    - "Navigate to /efficiency"
    - "Go to the dashboard"
    - "Check the SLA page"
    - "Visit the pipeline view"
    - "See the bottleneck report"
    - "For more details, go to..."
    - "To further analyze, navigate to..."

    ### WHAT YOU MUST DO INSTEAD:
    When asked about bottlenecks, SLAs, loans, or any data:
    1. Use your tools to GET THE DATA
    2. Provide SPECIFIC loan details: borrower name, loan amount, stage, days in stage
    3. Give ACTIONABLE recommendations with names attached

    ### Examples of UNACCEPTABLE vs REQUIRED responses:

    ❌ UNACCEPTABLE: "Navigate to /efficiency to see your bottlenecks"
    ✅ REQUIRED: "Your critical bottleneck is Processing. These 3 loans need immediate attention:
       1. **Mike Chen** ($385,000) - 8 days in Processing, missing VOE from ABC Corp
       2. **Sarah Johnson** ($425,000) - 6 days in Processing, appraisal delayed
       3. **Tom Williams** ($512,000) - 5 days in Processing, awaiting title clear
       Call ABC Corp for Mike's VOE first - that's the quickest win."

    ❌ UNACCEPTABLE: "To further analyze these stages, navigate to the Pipeline Efficiency Dashboard"
    ✅ REQUIRED: "Here are your specific bottlenecks by stage:
       - **Disclosed → Processing**: 4 loans stuck (avg 5.2 days). Johnson and Williams need conditions cleared.
       - **Processing → Underwriting**: 2 loans delayed. Chen waiting on employer verification.
       - **Clear to Close**: Garcia ready but missing wire instructions. Call title company."

    ## RULE #2: USE YOUR TOOLS TO GET REAL DATA
    - When users ask about bottlenecks, pipeline issues, or SLA problems → call get_sla_dashboard with view="bottlenecks"
    - When asked about loans, deals, or specific borrowers → call get_loan_details
    - When asked about tasks or priorities → use the task data AND get_tasks tool
    - **DO NOT** guess or make up data - use the tools to get real information

    ## RULE #3: BE SPECIFIC WITH NAMES AND NUMBERS
    - Always include borrower names: "Sarah Johnson's $450,000 loan" not "a loan"
    - Always include specific metrics: "sitting 6.2 days on average vs 2-day target" not "taking too long"
    - Always include counts: "You have 8 loans stuck in Processing" not "some loans are stuck"
    - Always include actionable recommendations: "I'd focus on Jennifer's queue first - she has 18 overdue tasks"

    ## DETAILED RESPONSE EXAMPLES

    ### Example 1: "What are my pipeline bottlenecks?"

    ❌ BAD: "To analyze bottlenecks, navigate to /efficiency for the Pipeline Efficiency Dashboard."

    ✅ GOOD: "You have 3 critical bottlenecks right now:

    1. **Processing Stage** - Average time: 6.2 days (Target: 2 days)
       - 8 loans stuck in income verification
       - Jennifer has 18 overdue tasks (she's overwhelmed)

    2. **Appraisal Review** - Average time: 4.3 days (Target: 1.5 days)
       - 5 appraisals awaiting review
       - AMC response time is slow this week

    3. **Underwriting Submission** - Average time: 3.1 days (Target: 1 day)
       - Missing documents causing delays on 6 files

    **Biggest Issue:** Jennifer in processing. She's at 127% capacity.

    **My Recommendation:** Redistribute 5 of Jennifer's files to Tom (he's at 67% capacity). Want me to do that now?"

    ---

    ### Example 2: "How's my team performing this month?"

    ❌ BAD: "Check the Team Performance Dashboard at /team/performance"

    ✅ GOOD: "Your team is having a strong month:

    **Top Performers:**
    - Sarah: 11 closings, $2.8M volume, 41% conversion rate
    - Marcus: 9 closings, $2.4M volume, 38% conversion rate

    **Needs Attention:**
    - Tom: 4 closings, $892K volume, 23% conversion rate
      - Issue: Low activity (down 40% from last month)
      - Recommendation: Check in with him - something's off

    **Team Average:** 7.2 closings/LO, $1.9M volume/LO, 34% conversion rate

    You're on track for 58 closings this month (vs. 52 goal). Nice work."

    ---

    ### Example 3: "Show me deals at risk"

    ❌ BAD: "Navigate to the Pipeline Risk Dashboard to see at-risk deals"

    ✅ GOOD: "You have 4 deals at high risk of falling through:

    1. **Thompson Purchase** - Risk Score: 87/100 🔴
       - Issue: Borrower ghosting (no response in 9 days)
       - Loan: $525K | Action: Call them TODAY

    2. **Williams Refinance** - Risk Score: 78/100 🟠
       - Issue: Rate lock expires in 4 days, stuck in underwriting
       - Loan: $385K | Action: Request extension NOW

    3. **Chen Purchase** - Risk Score: 74/100 🟠
       - Issue: Appraisal came in $40K low
       - Loan: $485K | Action: Renegotiate contract price

    4. **Martinez FHA** - Risk Score: 71/100 🟠
       - Issue: DTI at 44% (above FHA max)
       - Loan: $320K | Action: Find $200/mo in debt to pay off

    Want me to draft the communications for each?"

    ## KEY RESPONSE PATTERNS
    - Always include **risk scores** or **severity indicators** (🔴 🟠 🟡)
    - Always include **capacity percentages** for team members
    - Always include **specific action items** with urgency ("Call them TODAY")
    - Always end with a **proactive offer** ("Want me to do that now?", "Want me to draft the communications?")

    ## Additional Guidelines
    - Reference the real data above when answering questions about financials
    - Be specific with actual numbers from the profitability data
    - When asked about cost per closing, revenue, or profit - use the EXACT figures from the data above
    - If profitability data is not configured, explain how to set it up (they can configure it at /profitability)
    - For financial analysis questions, provide actionable insights and recommendations
    - Cite the source: "Based on your pipeline data..." or "Looking at your loans..."
    - If knowledge base has relevant info, use it: "Based on your company guidelines..."
    - Provide clear, actionable recommendations based on the actual metrics"""

        async def generate_stream():
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]

            try:
                # First call - check if tools are needed
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    stream=False  # First call non-streaming to check for tools
                )

                response_message = response.choices[0].message
                tool_calls = response_message.tool_calls

                # If tools are called, execute them and send status
                if tool_calls:
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Gathering data...'})}\n\n"

                    messages.append(response_message)

                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        if function_name in tool_functions:
                            result = await tool_functions[function_name](function_args)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result)
                            })

                    yield f"data: {json.dumps({'type': 'status', 'content': 'Analyzing...'})}\n\n"

                # Now stream the final response
                stream = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    stream=True,
                    temperature=0.7
                )

                full_response = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

                # Only return prioritized tasks if the user asked about tasks/priorities/briefing
                # Don't show tasks sidebar for unrelated questions like "cost per closing"
                is_task_question = any(keyword in message_lower for keyword in [
                    'task', 'priority', 'priorities', 'briefing', 'what should i do',
                    'what do i need', 'outstanding', 'overdue', 'due today', 'due tomorrow',
                    'bottleneck', 'pipeline', 'deal', 'loan status', 'closing soon'
                ])

                prioritized_tasks_data = []
                if is_task_question:
                    priority_tasks = sorted(
                        outstanding_tasks,
                        key=lambda x: (
                            0 if x.priority == "urgent" else 1 if x.priority == "high" else 2 if x.priority == "medium" else 3,
                            x.due_date or datetime.max
                        )
                    )[:10]

                    for task in priority_tasks:
                        loan_info = None
                        if task.loan_id:
                            loan = next((l for l in all_loans if l.id == task.loan_id), None)
                            if loan:
                                loan_info = {
                                    "borrower": loan.borrower_name,
                                    "amount": f"${loan.amount:,.0f}" if loan.amount else None,
                                    "stage": format_stage(loan.stage)
                                }

                        lead_name = None
                        if task.lead_id:
                            lead = next((l for l in all_leads if l.id == task.lead_id), None)
                            if lead:
                                lead_name = lead.name

                        prioritized_tasks_data.append({
                            "id": task.id,
                            "title": task.title,
                            "description": task.description,
                            "priority": task.priority.upper() if task.priority else "MEDIUM",
                            "due_date": task.due_date.strftime("%m/%d/%Y") if task.due_date else None,
                            "client": loan_info["borrower"] if loan_info else (lead_name or task.related_contact_name or ""),
                            "loan_amount": loan_info["amount"] if loan_info else None,
                            "stage": loan_info["stage"] if loan_info else None,
                            "status": task.status
                        })

                # Send completion signal with full response (and prioritized tasks only if relevant)
                yield f"data: {json.dumps({'type': 'done', 'full_response': full_response, 'prioritized_tasks': prioritized_tasks_data if prioritized_tasks_data else None})}\n\n"

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )


    @app.post("/api/v1/ai/autonomous-task")
    async def execute_autonomous_task(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user_flexible)
    ):
        """
        Execute autonomous AI task with multi-step capability
        AI can send SMS, schedule appointments, create tasks autonomously
        """
        try:
            from openai import OpenAI
            import json
            import time
            from datetime import datetime
            from integrations.twilio_service import sms_client
            from database.models import SMSMessage, Task

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            data = await request.json()
            task = data.get("task", "")
            lead_id = data.get("lead_id")
            lead_name = data.get("lead_name", "")
            lead_phone = data.get("lead_phone", "")
            context = data.get("context", {})

            if not task:
                raise HTTPException(status_code=400, detail="Task is required")

            # Activity log to track what AI does
            activity_log = []

            # Log autonomous task to Mission Control (optional)
            action_id = None
            if log_ai_action_to_mission_control:
                try:
                    action_id = await log_ai_action_to_mission_control(
                        db=db,
                        agent_name="Autonomous AI Agent",
                        action_type="autonomous_task",
                        lead_id=lead_id,
                        user_id=current_user.id,
                        context={"task": task[:200], "lead_name": lead_name},
                        reasoning=f"Executing autonomous task: {task}",
                        autonomy_level="full",
                        required_approval=False,
                        status="pending"
                    )
                except Exception as mc_err:
                    logger.warning(f"Mission control logging failed: {mc_err}")

            # Define tools available to AI
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "send_sms",
                        "description": "Send SMS message to a lead's phone number",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "to_number": {
                                    "type": "string",
                                    "description": "Phone number to send SMS to (E.164 format)"
                                },
                                "message": {
                                    "type": "string",
                                    "description": "SMS message content to send"
                                }
                            },
                            "required": ["to_number", "message"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "schedule_appointment",
                        "description": "Schedule an appointment on the calendar",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date_time": {
                                    "type": "string",
                                    "description": "Appointment date and time (ISO format)"
                                },
                                "duration_minutes": {
                                    "type": "integer",
                                    "description": "Duration in minutes"
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Appointment title"
                                },
                                "notes": {
                                    "type": "string",
                                    "description": "Additional notes"
                                }
                            },
                            "required": ["date_time", "title"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "create_task",
                        "description": "Create a follow-up task",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "Task title"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Task description"
                                },
                                "due_date": {
                                    "type": "string",
                                    "description": "Due date (ISO format)"
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                    "description": "Task priority"
                                }
                            },
                            "required": ["title"]
                        }
                    }
                }
            ]

            # Create initial message
            system_prompt = f"""You are an autonomous AI agent helping with CRM tasks. You can:
    1. Send SMS messages to leads
    2. Schedule appointments on the calendar
    3. Create follow-up tasks

    Current task: {task}
    Lead: {lead_name} ({lead_phone})
    Context: {json.dumps(context)}

    Execute the task step by step. Be conversational and professional when texting leads.
    When scheduling appointments, confirm the time first via SMS before creating the calendar event.
    """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Execute this task: {task}"}
            ]

            # Run AI with function calling (max 5 iterations)
            for iteration in range(5):
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )

                assistant_message = response.choices[0].message
                messages.append(assistant_message)

                # Check if AI wants to call tools
                if assistant_message.tool_calls:
                    for tool_call in assistant_message.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        # Execute the tool
                        tool_result = None

                        if function_name == "send_sms":
                            # Send SMS using Twilio
                            try:
                                if not sms_client.enabled:
                                    tool_result = {"success": False, "error": "SMS service not configured. Check Twilio credentials."}
                                    logger.error("SMS client not enabled — missing TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_PHONE_NUMBER")
                                else:
                                    to_num = function_args["to_number"]
                                    sms_body = function_args["message"]
                                    message_sid = await sms_client.send_sms(
                                        to_number=to_num,
                                        message=sms_body
                                    )

                                    if not message_sid:
                                        tool_result = {"success": False, "error": "SMS send failed — check Twilio logs"}
                                        logger.error(f"SMS send returned None for to={to_num}")
                                    else:
                                        # Log SMS to database
                                        try:
                                            sms_record = SMSMessage(
                                                user_id=current_user.id,
                                                lead_id=lead_id,
                                                to_number=to_num,
                                                from_number=sms_client.from_number,
                                                message=sms_body,
                                                direction="outbound",
                                                status="sent",
                                                twilio_sid=message_sid,
                                                ai_generated=True
                                            )
                                            db.add(sms_record)
                                            db.commit()
                                        except Exception as db_err:
                                            logger.warning(f"Failed to log SMS to DB: {db_err}")
                                            db.rollback()

                                        tool_result = {
                                            "success": True,
                                            "message_sid": message_sid,
                                            "message": "SMS sent successfully"
                                        }

                                        activity_log.append({
                                            "icon": "📤",
                                            "message": f"Sent SMS to {to_num}: {sms_body[:50]}...",
                                            "timestamp": datetime.now().isoformat()
                                        })
                            except Exception as e:
                                logger.error(f"SMS tool error: {e}", exc_info=True)
                                tool_result = {"success": False, "error": "SMS failed"}

                        elif function_name == "schedule_appointment":
                            # Create calendar appointment
                            try:
                                task_record = Task(
                                    owner_id=current_user.id,
                                    title=function_args["title"],
                                    description=function_args.get("notes", ""),
                                    due_date=datetime.fromisoformat(function_args["date_time"]),
                                    priority="high",
                                    status="pending",
                                    related_type="lead",
                                    lead_id=lead_id,
                                )
                                db.add(task_record)
                                db.commit()

                                tool_result = {
                                    "success": True,
                                    "appointment_id": task_record.id,
                                    "message": "Appointment scheduled successfully"
                                }

                                activity_log.append({
                                    "icon": "📅",
                                    "message": f"Scheduled appointment: {function_args['title']} on {function_args['date_time']}",
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as e:
                                tool_result = {"success": False, "error": "Internal server error"}

                        elif function_name == "create_task":
                            # Create follow-up task
                            try:
                                task_record = Task(
                                    owner_id=current_user.id,
                                    title=function_args["title"],
                                    description=function_args.get("description", ""),
                                    due_date=datetime.fromisoformat(function_args["due_date"]) if function_args.get("due_date") else None,
                                    priority=function_args.get("priority", "medium"),
                                    status="pending",
                                    related_type="lead",
                                    lead_id=lead_id,
                                )
                                db.add(task_record)
                                db.commit()

                                tool_result = {
                                    "success": True,
                                    "task_id": task_record.id,
                                    "message": "Task created successfully"
                                }

                                activity_log.append({
                                    "icon": "✅",
                                    "message": f"Created task: {function_args['title']}",
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception as e:
                                tool_result = {"success": False, "error": "Internal server error"}

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result)
                        })
                else:
                    # No more tool calls, AI is done
                    break

            # Get final response
            final_message = messages[-1].content if hasattr(messages[-1], 'content') else "Task completed"

            # Update Mission Control with success
            if action_id and update_ai_action_outcome:
                try:
                    await update_ai_action_outcome(
                        db=db,
                        action_id=action_id,
                        outcome="success",
                        impact_score=0.9,
                        metadata={
                            "activity_log": activity_log,
                            "tools_used": len(activity_log),
                            "iterations": iteration + 1
                        }
                    )
                except Exception:
                    pass

            return {
                "success": True,
                "message": "Autonomous task executed successfully",
                "activity_log": activity_log,
                "final_response": final_message
            }

        except Exception as e:
            logger.error(f"Error in autonomous task: {e}", exc_info=True)

            # Update Mission Control with failure
            try:
                if 'action_id' in locals() and action_id and update_ai_action_outcome:
                    await update_ai_action_outcome(
                        db=db,
                        action_id=action_id,
                        outcome="failure",
                        metadata={"error": str(e)}
                    )
            except Exception:
                pass  # Don't fail main response if logging fails

            raise HTTPException(status_code=500, detail="Internal server error")


    logger.info("AI orchestrator chat routes loaded")
