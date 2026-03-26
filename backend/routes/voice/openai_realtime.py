"""
Voice Routes - OpenAI Realtime API Connection Management

Contains:
- connect_to_openai_realtime: Connect for Telnyx (g711_ulaw format)
- connect_to_openai_realtime_browser: Connect for browser (PCM16 format)
- extract_lead_info: Extract lead data from transcripts using Claude
"""
import os
import logging
import json
import asyncio

import openai

from .utils import voice_client, ai_config

logger = logging.getLogger(__name__)


async def connect_to_openai_realtime_browser():
    """Connect to OpenAI Realtime API for browser (PCM16 format)"""
    import websockets

    openai_api_key = os.getenv("OPENAI_API_KEY") or openai.api_key
    if not openai_api_key:
        raise Exception("OpenAI API key not configured")

    logger.info("Connecting to OpenAI Realtime API for browser...")

    url = f"wss://api.openai.com/v1/realtime?model={os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-12-17')}"

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    ws = await asyncio.wait_for(
        websockets.connect(url, additional_headers=headers),
        timeout=10.0
    )

    # Wait for session.created
    initial_response = await asyncio.wait_for(ws.recv(), timeout=5.0)
    logger.info(f"OpenAI Realtime connected: {initial_response[:200]}")

    # Configure session for browser audio (PCM16 at 24kHz)
    # Use same voice and settings as phone for consistent experience
    # Browser voice is used by the LO directly — tools enable CRM actions via voice
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": ai_config.system_prompt.format(business_name=ai_config.business_name),
            "voice": "coral",  # Same warm, natural voice as phone calls
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            },
            "tools": [
                {
                    "type": "function",
                    "name": "search_contact",
                    "description": "Search for a contact or lead by name in the CRM. Returns name, phone, email, and lead ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Contact name to search for (e.g. 'Phil George')"}
                        },
                        "required": ["name"]
                    }
                },
                {
                    "type": "function",
                    "name": "send_sms",
                    "description": "Send an SMS text message to a contact. Requires phone number and message text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone_number": {"type": "string", "description": "Phone number in E.164 format (e.g. +14155551234)"},
                            "message": {"type": "string", "description": "The text message content to send"},
                            "contact_name": {"type": "string", "description": "Name of the recipient for logging"}
                        },
                        "required": ["phone_number", "message"]
                    }
                },
                {
                    "type": "function",
                    "name": "get_my_availability",
                    "description": "Get the loan officer's available time slots for scheduling meetings.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "days_ahead": {"type": "integer", "description": "Number of days ahead to check (default 5)", "default": 5},
                            "duration_minutes": {"type": "integer", "description": "Meeting duration in minutes (default 30)", "default": 30}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "schedule_appointment",
                    "description": "Book an appointment on the loan officer's calendar with a contact.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_name": {"type": "string", "description": "Name of the person to meet with"},
                            "contact_email": {"type": "string", "description": "Email of the contact (optional)"},
                            "contact_phone": {"type": "string", "description": "Phone of the contact (optional)"},
                            "date": {"type": "string", "description": "Date for the appointment (YYYY-MM-DD)"},
                            "time": {"type": "string", "description": "Time for the appointment (HH:MM in 24h format)"},
                            "duration_minutes": {"type": "integer", "description": "Duration in minutes (default 30)", "default": 30},
                            "meeting_type": {"type": "string", "description": "Type: discovery_call, pre_approval_review, rate_lock_discussion, custom", "default": "discovery_call"},
                            "reason": {"type": "string", "description": "Reason/notes for the appointment"}
                        },
                        "required": ["contact_name", "date", "time"]
                    }
                },
                {
                    "type": "function",
                    "name": "create_task",
                    "description": "Create a task or to-do item for the loan officer.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Task title"},
                            "description": {"type": "string", "description": "Task description/details"},
                            "due_date": {"type": "string", "description": "Due date (YYYY-MM-DD)"},
                            "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"}
                        },
                        "required": ["title"]
                    }
                },
                {
                    "type": "function",
                    "name": "start_scheduling_workflow",
                    "description": "Start an autonomous scheduling workflow: sends SMS to a contact with available times, then AI negotiates meeting time via text conversation and books the appointment automatically.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_name": {"type": "string", "description": "Name of the person to schedule with"},
                            "contact_phone": {"type": "string", "description": "Phone number to text (E.164 format)"},
                            "meeting_type": {"type": "string", "description": "Type of meeting", "default": "discovery_call"},
                            "message_context": {"type": "string", "description": "Additional context for the initial SMS (e.g. 'discuss rate options')"}
                        },
                        "required": ["contact_name", "contact_phone"]
                    }
                },
                {
                    "type": "function",
                    "name": "get_pipeline_summary",
                    "description": "Get a summary of the loan officer's current pipeline including active loans, volume, and key metrics.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "type": "function",
                    "name": "get_recent_call_summary",
                    "description": "Get the AI-generated summary and action items from the most recent call intelligence session.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Specific CI session ID. If omitted, uses most recent."}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "get_call_artifacts",
                    "description": "Get specific artifacts from a call intelligence session — action items, document requests, risk flags, or all.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "artifact_type": {"type": "string", "enum": ["summary", "action_item", "document_request", "risk_flag", "intake_field", "all"], "description": "Type of artifacts to retrieve"},
                            "session_id": {"type": "string", "description": "CI session ID. Omit for most recent."}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "send_email",
                    "description": "Send an email to a contact. Requires email address, subject, and body.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject line"},
                            "body": {"type": "string", "description": "Email body text"},
                            "contact_name": {"type": "string", "description": "Recipient name for logging"}
                        },
                        "required": ["email", "subject", "body"]
                    }
                },
                {
                    "type": "function",
                    "name": "complete_task",
                    "description": "Mark a task as completed by its title or ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_title": {"type": "string", "description": "Title or partial title of the task to complete"},
                            "task_id": {"type": "string", "description": "Task ID if known"}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "approve_artifact",
                    "description": "Approve a call intelligence artifact for execution. Say the artifact title or type to approve.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "artifact_id": {"type": "string", "description": "Artifact ID to approve"},
                            "artifact_title": {"type": "string", "description": "Partial title match if ID unknown"}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "execute_artifacts",
                    "description": "Execute all approved artifacts from a call intelligence session — creates tasks, sends documents, schedules follow-ups.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "CI session ID. Omit for most recent."}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "start_call_recording",
                    "description": "Start recording and analyzing a call with Call Intelligence. Activates real-time transcription and AI analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name": {"type": "string", "description": "Name of the person on the call, if known"},
                            "client_phone": {"type": "string", "description": "Phone number of the person, if known"},
                            "context": {"type": "string", "description": "Brief context like 'rate inquiry' or 'application follow-up'"}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "stop_call_recording",
                    "description": "Stop the current call recording and trigger AI agent analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "CI session ID to stop. Omit for current active session."}
                        }
                    }
                },
                {
                    "type": "function",
                    "name": "send_document_checklist",
                    "description": "Send the document checklist from a call intelligence session to the borrower via SMS or email.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "CI session ID. Omit for most recent."},
                            "send_via": {"type": "string", "enum": ["sms", "email", "both"], "description": "How to send the checklist", "default": "sms"},
                            "recipient_phone": {"type": "string", "description": "Phone number to send SMS to"},
                            "recipient_email": {"type": "string", "description": "Email to send to"}
                        }
                    }
                }
            ]
        }
    }))

    return ws


async def connect_to_openai_realtime():
    """Connect to OpenAI Realtime API WebSocket"""
    import websockets

    openai_api_key = os.getenv("OPENAI_API_KEY") or openai.api_key
    if not openai_api_key:
        raise Exception("OpenAI API key not configured")

    logger.info("Connecting to OpenAI Realtime API")

    # Use configurable model name - defaults to pinned version
    url = f"wss://api.openai.com/v1/realtime?model={os.getenv('OPENAI_REALTIME_MODEL', 'gpt-4o-realtime-preview-2024-12-17')}"

    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    # Connect with timeout - use additional_headers (websockets 10.x+)
    ws = await asyncio.wait_for(
        websockets.connect(url, additional_headers=headers),
        timeout=10.0
    )

    # Wait for session.created event with timeout
    initial_response = await asyncio.wait_for(ws.recv(), timeout=5.0)
    logger.info(f"OpenAI Realtime initial response: {initial_response[:500]}")

    # Check for error in initial response
    try:
        initial_data = json.loads(initial_response)
        if initial_data.get('type') == 'error':
            error_msg = initial_data.get('error', {}).get('message', 'Unknown error')
            error_code = initial_data.get('error', {}).get('code', 'unknown')
            logger.error(f"OpenAI Realtime error: {error_code} - {error_msg}")
            raise Exception(f"OpenAI error: {error_code} - {error_msg}")
        logger.info(f"OpenAI Realtime session created: {initial_data.get('type')}")
    except json.JSONDecodeError:
        logger.warning(f"Could not parse initial response as JSON: {initial_response[:200]}")

    # Configure the session for natural two-way conversation
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": ai_config.system_prompt.format(business_name=ai_config.business_name),
            "voice": "coral",  # Natural, warm voice for phone conversations
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,  # Balanced - detects speech but filters some noise
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500  # Faster response
            },
            "tools": [
                {
                    "type": "function",
                    "name": "schedule_appointment",
                    "description": "Schedule an appointment with a loan officer",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Preferred date (YYYY-MM-DD)"},
                            "time": {"type": "string", "description": "Preferred time (HH:MM)"},
                            "reason": {"type": "string", "description": "Reason for appointment"}
                        },
                        "required": ["date", "time"]
                    }
                },
                {
                    "type": "function",
                    "name": "transfer_to_loan_officer",
                    "description": "Transfer call to a loan officer for urgent matters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Reason for transfer"},
                            "urgency": {"type": "string", "enum": ["low", "medium", "high"]}
                        },
                        "required": ["reason"]
                    }
                },
                {
                    "type": "function",
                    "name": "take_message",
                    "description": "Take a message for the team",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "phone": {"type": "string"},
                            "message": {"type": "string"},
                            "callback_urgency": {"type": "string", "enum": ["urgent", "today", "this_week"]}
                        },
                        "required": ["name", "phone", "message"]
                    }
                }
            ]
        }
    }))

    logger.info("OpenAI Realtime session configured")

    # NOTE: We no longer trigger greeting here - it's done in telnyx_to_openai()
    # when we receive the 'start' event from Telnyx (meaning it's ready to receive audio)

    return ws


async def extract_lead_info(transcript: str, call_context: dict):
    """Extract lead information from conversation using Claude"""
    try:
        # Use Claude to extract structured data from conversation
        import anthropic

        client = anthropic.Anthropic()

        prompt = f"""Extract lead information from this phone conversation transcript:

{transcript}

Previous context: {json.dumps(call_context['conversation_history'][-5:])}

Extract and return JSON with:
- name: caller's name (if mentioned)
- phone: phone number (if mentioned)
- loan_type: purchase/refinance/cash-out/heloc (if discussed)
- property_value: estimated value (if mentioned)
- credit_score: range if mentioned
- urgency: low/medium/high based on timeline
- intent: what they want (quote/appointment/question/etc)

Return ONLY valid JSON, no other text."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        lead_data = json.loads(message.content[0].text)
        call_context['lead_data'].update(lead_data)

        logger.info(f"Extracted lead data: {lead_data}")

    except Exception as e:
        logger.error(f"Error extracting lead info: {e}")
