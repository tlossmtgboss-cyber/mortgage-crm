"""Voice tool handlers for Call Intelligence operations.

These functions are called by the OpenAI Realtime function-call pipeline
when the LO uses voice commands related to Call Intelligence.
All handlers follow the same signature: (args, db, organization_id, user_id) -> dict
"""

import logging

logger = logging.getLogger(__name__)


async def handle_start_call_recording(args: dict, db, organization_id, user_id) -> dict:
    """Start a new Call Intelligence session."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    session_id = await bridge.start_ci_session(
        context=args.get("context"),
        client_name=args.get("client_name"),
        client_phone=args.get("client_phone"),
    )
    return {
        "success": True,
        "session_id": session_id,
        "message": "Call Intelligence recording started. I'll analyze the conversation in real-time.",
    }


async def handle_stop_call_recording(args: dict, db, organization_id, user_id) -> dict:
    """Stop the current CI session and trigger processing."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    result = await bridge.stop_ci_session(
        session_id=args.get("session_id"),
        run_agents=True,
    )
    if result.get("success"):
        return {
            "success": True,
            "message": "Recording stopped. AI agents are now analyzing the call.",
            "session_id": result.get("session_id"),
        }
    return {"success": False, "message": result.get("error", "Failed to stop recording")}


async def handle_get_recent_call_summary(args: dict, db, organization_id, user_id) -> dict:
    """Get summary from the most recent CI session."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    summary = await bridge.get_session_summary(session_id=args.get("session_id"))
    if summary.get("error"):
        return {"success": False, "message": summary["error"]}

    # Format for voice readback
    msg_parts = []
    if summary.get("summary"):
        msg_parts.append(summary["summary"][:500])  # Truncate for voice

    action_items = summary.get("action_items", [])
    if action_items:
        msg_parts.append(f"There are {len(action_items)} action items.")
        for i, item in enumerate(action_items[:3], 1):
            msg_parts.append(f"{i}. {item['title']}")

    msg_parts.append(f"Total artifacts: {summary.get('total_artifacts', 0)}")

    return {
        "success": True,
        "message": " ".join(msg_parts),
        "summary": summary,
    }


async def handle_get_call_artifacts(args: dict, db, organization_id, user_id) -> dict:
    """Get artifacts from a CI session."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    artifacts = await bridge.get_artifacts(
        session_id=args.get("session_id"),
        artifact_type=args.get("artifact_type"),
    )

    if not artifacts:
        return {"success": True, "message": "No artifacts found.", "artifacts": [], "count": 0}

    # Format for voice readback
    msg = f"Found {len(artifacts)} artifacts. "
    for i, a in enumerate(artifacts[:5], 1):
        msg += f"{i}. {a['title']} ({a['type'].replace('_', ' ')}). "

    return {
        "success": True,
        "message": msg,
        "artifacts": artifacts,
        "count": len(artifacts),
    }


async def handle_approve_artifact(args: dict, db, organization_id, user_id) -> dict:
    """Approve a CI artifact."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    result = await bridge.approve_artifact(
        artifact_id=args.get("artifact_id"),
        title_match=args.get("artifact_title"),
    )
    if result.get("success"):
        return {
            "success": True,
            "message": f"Approved: {result.get('title', 'artifact')}",
        }
    return {"success": False, "message": result.get("error", "Could not approve artifact")}


async def handle_execute_artifacts(args: dict, db, organization_id, user_id) -> dict:
    """Execute all approved artifacts."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    result = await bridge.execute_approved(session_id=args.get("session_id"))
    if result.get("success"):
        return {
            "success": True,
            "message": f"Executed {result.get('count', 0)} artifacts. " +
                       ", ".join(r.get('title', '') for r in result.get('results', [])[:3]),
        }
    return {"success": False, "message": result.get("error", "Failed to execute artifacts")}


async def handle_send_document_checklist(args: dict, db, organization_id, user_id) -> dict:
    """Send document checklist from CI session to borrower."""
    from services.voice_ci_bridge_service import VoiceCIBridgeService
    bridge = VoiceCIBridgeService(db, organization_id, user_id)
    checklist = await bridge.get_document_checklist(session_id=args.get("session_id"))

    if not checklist.get("documents"):
        return {"success": False, "message": "No document requests found in the call intelligence session."}

    # Build checklist text
    doc_list = "\n".join(
        f"- {doc['title']}" + (f": {doc['details']}" if doc.get('details') else "")
        for doc in checklist["documents"]
    )
    checklist_text = f"Document checklist from your recent call:\n{doc_list}\n\nPlease send these at your earliest convenience."

    send_via = args.get("send_via", "sms")
    recipient_phone = args.get("recipient_phone")
    recipient_email = args.get("recipient_email")

    if send_via in ("sms", "both") and recipient_phone:
        import os
        try:
            import telnyx
            telnyx.api_key = os.getenv("TELNYX_API_KEY")
            telnyx_from = os.getenv("TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""))
            messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

            send_params = {"from_": telnyx_from, "to": recipient_phone, "text": checklist_text}
            if messaging_profile_id:
                send_params["messaging_profile_id"] = messaging_profile_id
            telnyx.Message.create(**send_params)

            logger.info(f"Document checklist sent via SMS to {recipient_phone[-4:]}")
        except Exception as e:
            logger.error(f"Failed to send checklist SMS: {e}")
            return {"success": False, "message": f"Failed to send SMS: {str(e)}"}

    return {
        "success": True,
        "message": f"Document checklist with {checklist['count']} items sent to the borrower.",
        "documents_sent": checklist["count"],
    }


# Dispatch map for use from tool_handlers.py
CI_TOOL_HANDLERS = {
    "start_call_recording": handle_start_call_recording,
    "stop_call_recording": handle_stop_call_recording,
    "get_recent_call_summary": handle_get_recent_call_summary,
    "get_call_artifacts": handle_get_call_artifacts,
    "approve_artifact": handle_approve_artifact,
    "execute_artifacts": handle_execute_artifacts,
    "send_document_checklist": handle_send_document_checklist,
}
