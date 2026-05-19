"""
ToolDispatchMixin — tool definitions catalog, tool execution, and
post-execution tenant validation.

Extracted from the original monolithic AIAgentService (Wave 3 decomposition).
Mechanical method-move only; bodies and signatures are unchanged.

Shared state expected on self:
    self._tool_functions          — Dict[str, Callable]
    self._tool_definitions        — List[Dict]
    self.current_user             — authenticated user (for tenant validation)
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ToolDispatchMixin:
    """Tool-definition catalog, dispatch, and tenant-aware result validation."""

    def _get_tool_definitions(self) -> List[Dict]:
        """Get tool definitions for the API call."""
        if self._tool_definitions:
            return self._tool_definitions

        # Default tool definitions based on registered functions
        definitions = []

        if "get_pipeline" in self._tool_functions:
            definitions.append({
                "name": "get_pipeline",
                "description": "Get pipeline summary with leads and loans by stage",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "include_details": {
                            "type": "boolean",
                            "description": "Include detailed loan/lead info"
                        }
                    }
                }
            })

        if "get_tasks" in self._tool_functions:
            definitions.append({
                "name": "get_tasks",
                "description": "Get user's tasks with optional time filtering",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "timeframe": {
                            "type": "string",
                            "enum": ["today", "tomorrow", "this_week", "overdue", "all"],
                            "description": "Time filter for tasks"
                        }
                    }
                }
            })

        if "search_leads" in self._tool_functions:
            definitions.append({
                "name": "search_leads",
                "description": "Search for leads by name, email, or phone",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            })

        if "search_loans" in self._tool_functions:
            definitions.append({
                "name": "search_loans",
                "description": "Search for loans by borrower name, loan number, or property address",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            })

        if "create_task" in self._tool_functions:
            definitions.append({
                "name": "create_task",
                "description": "Create a new task for the user",
                "input_schema": {
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
                            "description": "Due date in ISO format"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Task priority"
                        },
                        "loan_id": {
                            "type": "integer",
                            "description": "Associated loan ID"
                        },
                        "lead_id": {
                            "type": "integer",
                            "description": "Associated lead ID"
                        }
                    },
                    "required": ["title"]
                }
            })

        if "get_pipeline_metrics" in self._tool_functions:
            definitions.append({
                "name": "get_pipeline_metrics",
                "description": "Get pipeline analytics and metrics",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            })

        if "get_rate_lock_advisory" in self._tool_functions:
            definitions.append({
                "name": "get_rate_lock_advisory",
                "description": "Get rate lock advisory based on market conditions",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days_to_close": {
                            "type": "integer",
                            "description": "Days until closing",
                            "default": 30
                        }
                    }
                }
            })

        if "get_daily_priorities" in self._tool_functions:
            definitions.append({
                "name": "get_daily_priorities",
                "description": "Get prioritized list of actions for today",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            })

        if "get_emails_needing_response" in self._tool_functions:
            definitions.append({
                "name": "get_emails_needing_response",
                "description": "Get emails from your inbox that need a response. Shows unread/pending emails requiring attention. Use this when user asks about emails to respond to, inbox status, or unread emails.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back",
                            "default": 7
                        },
                        "unread_only": {
                            "type": "boolean",
                            "description": "Only show unread/pending emails",
                            "default": True
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of emails to return",
                            "default": 20
                        }
                    }
                }
            })

        # Communication tools
        if "send_sms" in self._tool_functions:
            definitions.append({
                "name": "send_sms",
                "description": "Send an SMS text message to a phone number. Use search_leads first to find the contact's phone number if not provided.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "Recipient phone number (any format)"},
                        "message": {"type": "string", "description": "Text message to send"},
                        "lead_id": {"type": "integer", "description": "Associated lead ID for CRM tracking"}
                    },
                    "required": ["phone_number", "message"]
                }
            })

        if "click_to_dial" in self._tool_functions:
            definitions.append({
                "name": "click_to_dial",
                "description": "Initiate an outbound phone call to a contact. Use search_leads first to find the contact's phone number if not provided.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "Phone number to call"},
                        "contact_name": {"type": "string", "description": "Name of the person being called"},
                        "lead_id": {"type": "integer", "description": "Associated lead ID"}
                    },
                    "required": ["phone_number"]
                }
            })

        if "send_email" in self._tool_functions:
            definitions.append({
                "name": "send_email",
                "description": "Send an email via Microsoft Graph (from the LO's Outlook). Auto-injects calendar availability for scheduling emails.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to_email": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email body content"},
                        "skip_availability": {"type": "boolean", "description": "Skip auto-injecting calendar availability"}
                    },
                    "required": ["to_email", "body"]
                }
            })

        # Lead insight tools
        if "lead_status_insights" in self._tool_functions:
            definitions.append({
                "name": "lead_status_insights",
                "description": "Get detailed insights about leads in a specific stage including count, recent activity, and aging stats.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Lead stage to analyze (e.g., New, Contacted, Qualified)"}
                    },
                    "required": ["status"]
                }
            })

        if "get_leads_by_status" in self._tool_functions:
            definitions.append({
                "name": "get_leads_by_status",
                "description": "Get a list of leads filtered by pipeline stage with contact info and last activity.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Lead stage to filter by"},
                        "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20}
                    },
                    "required": ["status"]
                }
            })

        if "get_top_leads" in self._tool_functions:
            definitions.append({
                "name": "get_top_leads",
                "description": "Get highest-scoring leads ranked by AI score, engagement, and conversion potential.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of top leads to return (default 10)", "default": 10}
                    }
                }
            })

        if "get_stale_leads" in self._tool_functions:
            definitions.append({
                "name": "get_stale_leads",
                "description": "Get leads that haven't been contacted recently and need follow-up attention.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days_threshold": {"type": "integer", "description": "Days since last contact to consider stale (default 7)", "default": 7},
                        "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20}
                    }
                }
            })

        # Bulk outreach
        if "bulk_lead_outreach" in self._tool_functions:
            definitions.append({
                "name": "bulk_lead_outreach",
                "description": "Send personalized SMS to multiple leads by stage and create follow-up tasks for non-responders.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "lead_status": {"type": "string", "description": "Stage of leads to contact (e.g., NEW, ATTEMPTED_CONTACT)"},
                        "message_template": {"type": "string", "description": "Message to send. Use {name} for personalization."},
                        "include_calendar_link": {"type": "boolean", "description": "Include booking link in message"},
                        "create_followup_tasks": {"type": "boolean", "description": "Create follow-up tasks for non-responders"}
                    },
                    "required": ["lead_status"]
                }
            })

        # Email and partner tools
        if "search_email_inbox" in self._tool_functions:
            definitions.append({
                "name": "search_email_inbox",
                "description": "Search the user's email inbox for messages matching a query. Returns subject, from, date, and preview.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (name, subject, keyword)"},
                        "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10}
                    },
                    "required": ["query"]
                }
            })

        if "create_referral_partner" in self._tool_functions:
            definitions.append({
                "name": "create_referral_partner",
                "description": "Add a realtor, attorney, or other referral partner to the CRM. Use this when the LO mentions a partner who isn't in the system yet. Requires name plus at least phone or email. After creating, send them an SMS with the portal link (app.perenniaai.com/realtor-portal).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Partner's full name"},
                        "company": {"type": "string", "description": "Company name"},
                        "email": {"type": "string", "description": "Partner's email (optional if phone provided)"},
                        "phone": {"type": "string", "description": "Partner's phone number (optional if email provided)"},
                        "partner_type": {"type": "string", "description": "Type: realtor, financial_advisor, attorney, insurance, builder, other"}
                    },
                    "required": ["name"]
                }
            })

        return definitions

    async def _execute_tool(self, tool_name: str, args: Dict) -> Dict[str, Any]:
        """Execute a registered tool and return its result.

        Includes post-execution tenant validation: any result rows containing
        an organization_id field are checked against the current user's org.
        Cross-tenant rows are stripped and logged as a security violation.
        """
        if tool_name not in self._tool_functions:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            func = self._tool_functions[tool_name]
            result = await func(args)

            # Post-execution tenant validation (defense-in-depth)
            result = self._validate_tool_result_tenant(tool_name, result)

            return result
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {"error": "Internal server error"}

    def _validate_tool_result_tenant(self, tool_name: str, result: Any) -> Any:
        """Validate that tool results belong to the current user's organization.

        Strips any items with a mismatched organization_id and logs violations.
        This is a defense-in-depth measure — tool queries should already be
        scoped by RLS and query-level filters, but this catches edge cases.
        """
        if not result or not isinstance(result, dict):
            return result

        org_id = getattr(self.current_user, 'organization_id', None)
        if org_id is None:
            return result

        # Check list-valued fields (e.g., "leads", "loans", "results", "tasks", "items")
        _LIST_KEYS = ("leads", "loans", "results", "tasks", "items", "data", "records", "entries")
        for key in _LIST_KEYS:
            items = result.get(key)
            if not isinstance(items, list):
                continue

            pre_count = len(items)
            filtered = [
                item for item in items
                if not isinstance(item, dict)
                or item.get("organization_id") is None
                or item.get("organization_id") == org_id
            ]
            removed = pre_count - len(filtered)
            if removed > 0:
                logger.critical(
                    f"[TENANT-TOOL] Stripped {removed} cross-tenant rows from "
                    f"tool={tool_name} key={key} (org_id={org_id}). "
                    f"This indicates a query scoping gap."
                )
                result[key] = filtered
                # Update count fields if present
                if "count" in result:
                    result["count"] = len(filtered)
                if "total" in result:
                    result["total"] = len(filtered)

        # Check top-level organization_id on single-record results
        if "organization_id" in result and result["organization_id"] is not None:
            if result["organization_id"] != org_id:
                logger.critical(
                    f"[TENANT-TOOL] Blocked cross-tenant result from "
                    f"tool={tool_name} (result org_id={result['organization_id']}, "
                    f"expected={org_id})"
                )
                return {"error": "No matching data found.", "count": 0}

        return result
