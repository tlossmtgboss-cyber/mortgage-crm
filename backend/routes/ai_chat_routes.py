"""
AI Chat Routes — Autonomous Task Execution

Provides the autonomous-task endpoint for multi-step AI task execution.

NOTE: The orchestrator-chat-stream endpoint formerly in this file has been
removed. The canonical version lives in ai_orchestrator_routes.py.
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import os

logger = logging.getLogger(__name__)


def register_ai_chat_routes(app, get_db, get_current_user_flexible, **kwargs):
    """Register AI chat routes (autonomous task execution)."""
    from database.models import User

    # Extract functions passed from main.py via kwargs
    log_ai_action_to_mission_control = kwargs.get('log_ai_action_to_mission_control')
    update_ai_action_outcome = kwargs.get('update_ai_action_outcome')

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
            from integrations.sms_service import get_sms_client
            sms_client = get_sms_client()
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
                            # Send SMS using configured provider (Telnyx)
                            try:
                                if not sms_client.enabled:
                                    tool_result = {"success": False, "error": f"SMS service not configured. Check {sms_client.provider} credentials."}
                                    logger.error(f"SMS client not enabled — provider={sms_client.provider}")
                                else:
                                    to_num = function_args["to_number"]
                                    sms_body = function_args["message"]
                                    message_sid = await sms_client.send_sms(
                                        to_number=to_num,
                                        message=sms_body
                                    )

                                    if not message_sid:
                                        tool_result = {"success": False, "error": f"SMS send failed — check {sms_client.provider} logs"}
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
                                                provider_message_id=message_sid,
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
                                            "icon": "sent",
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
                                    "icon": "calendar",
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
                                    "icon": "check",
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
                except Exception as e:
                    logger.warning(f"Error updating AI action outcome on success: {e}")

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
                        metadata={"error": "Task execution failed"}
                    )
            except Exception as e:
                logger.warning(f"Error updating AI action outcome on failure: {e}")

            raise HTTPException(status_code=500, detail="Internal server error")


    logger.info("AI chat routes loaded (autonomous-task only)")
