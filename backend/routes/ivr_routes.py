"""
IVR (Interactive Voice Response) Routes
Implements IVR menus with DTMF support for call routing
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from enum import Enum
import logging
import json
import os

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ivr", tags=["ivr"])


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_async_db)):
    """
    Optional authentication - returns user if authenticated, None otherwise.
    Lazy imports from main to avoid circular imports.
    """
    try:
        from auth.dependencies import get_current_user_flexible as auth_func
        return await auth_func(request, db)
    except Exception as e:
        logger.debug(f"Auth failed (optional): {e}")
        return None


# ============================================================================
# ENUMS AND MODELS
# ============================================================================

class IVRActionType(str, Enum):
    TRANSFER_USER = "transfer_user"  # Transfer to internal user
    TRANSFER_PHONE = "transfer_phone"  # Transfer to external number
    TRANSFER_QUEUE = "transfer_queue"  # Transfer to call queue
    SUBMENU = "submenu"  # Go to another IVR menu
    VOICEMAIL = "voicemail"  # Go to voicemail
    AI_RECEPTIONIST = "ai_receptionist"  # Connect to AI
    PLAY_MESSAGE = "play_message"  # Play a message and return
    HANGUP = "hangup"  # End the call
    REPEAT = "repeat"  # Repeat the menu


class IVRMenuCreate(BaseModel):
    """Create IVR menu"""
    name: str
    description: Optional[str] = None
    is_default: bool = False
    greeting_text: Optional[str] = None
    greeting_audio_url: Optional[str] = None
    timeout_seconds: int = 10
    max_attempts: int = 3
    timeout_action: str = "transfer_receptionist"


class IVRMenuUpdate(BaseModel):
    """Update IVR menu"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    greeting_text: Optional[str] = None
    greeting_audio_url: Optional[str] = None
    timeout_seconds: Optional[int] = None
    max_attempts: Optional[int] = None
    timeout_action: Optional[str] = None


class IVROptionCreate(BaseModel):
    """Create IVR menu option"""
    dtmf_digit: str = Field(..., min_length=1, max_length=1, pattern=r'^[0-9*#]$')
    label: str
    action_type: IVRActionType
    action_target: Optional[str] = None  # User ID, phone, queue name, menu ID
    announcement_text: Optional[str] = None
    display_order: int = 0


class IVROptionUpdate(BaseModel):
    """Update IVR menu option"""
    label: Optional[str] = None
    action_type: Optional[IVRActionType] = None
    action_target: Optional[str] = None
    announcement_text: Optional[str] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


# ============================================================================
# IVR MENU CRUD ENDPOINTS
# ============================================================================

@router.post("/menus")
async def create_ivr_menu(
    menu: IVRMenuCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Create a new IVR menu"""
    try:
        # If setting as default, unset other defaults
        if menu.is_default:
            await db.execute(text("UPDATE ivr_menus SET is_default = FALSE WHERE is_default = TRUE"))

        result = await db.execute(text("""
            INSERT INTO ivr_menus
            (name, description, is_default, greeting_text, greeting_audio_url,
             timeout_seconds, max_attempts, timeout_action, created_by, is_active)
            VALUES
            (:name, :description, :is_default, :greeting_text, :greeting_audio_url,
             :timeout_seconds, :max_attempts, :timeout_action, :created_by, TRUE)
            RETURNING id
        """), {
            "name": menu.name,
            "description": menu.description,
            "is_default": menu.is_default,
            "greeting_text": menu.greeting_text,
            "greeting_audio_url": menu.greeting_audio_url,
            "timeout_seconds": menu.timeout_seconds,
            "max_attempts": menu.max_attempts,
            "timeout_action": menu.timeout_action,
            "created_by": current_user.id if current_user else None
        })

        try:
            menu_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in create_ivr_menu: {e}")
            menu_id = result.lastrowid or await db.execute(text("SELECT last_insert_rowid()")).scalar()

        await db.commit()

        return {
            "success": True,
            "message": "IVR menu created",
            "menu_id": menu_id
        }

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating IVR menu: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/menus")
async def list_ivr_menus(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """List all IVR menus"""
    try:
        where_clause = "" if include_inactive else "WHERE m.is_active = TRUE"

        sql = (
            "SELECT m.id, m.name, m.description, m.is_default, m.is_active,"
            " m.greeting_text, m.greeting_audio_url, m.timeout_seconds,"
            " m.max_attempts, m.timeout_action, m.created_at,"
            " COUNT(o.id) as option_count"
            " FROM ivr_menus m"
            " LEFT JOIN ivr_menu_options o ON o.menu_id = m.id AND o.is_active = TRUE"
            " " + where_clause +
            " GROUP BY m.id"
            " ORDER BY m.is_default DESC, m.name ASC"
        )
        results = await db.execute(text(sql)).fetchall()

        menus = []
        for row in results:
            created_at = None
            if hasattr(row, 'created_at') and row.created_at:
                if hasattr(row.created_at, 'isoformat'):
                    created_at = row.created_at.isoformat()
                else:
                    created_at = str(row.created_at)

            menus.append({
                "id": row.id,
                "name": row.name,
                "description": getattr(row, 'description', None),
                "is_default": getattr(row, 'is_default', False),
                "is_active": getattr(row, 'is_active', True),
                "greeting_text": getattr(row, 'greeting_text', None),
                "greeting_audio_url": getattr(row, 'greeting_audio_url', None),
                "timeout_seconds": getattr(row, 'timeout_seconds', 10),
                "max_attempts": getattr(row, 'max_attempts', 3),
                "timeout_action": getattr(row, 'timeout_action', 'ai_receptionist'),
                "option_count": getattr(row, 'option_count', 0),
                "created_at": created_at
            })

        return {
            "menus": menus,
            "count": len(menus)
        }

    except SQLAlchemyError as e:
        # Table might not exist
        logger.warning(f"Database error listing IVR menus (table may not exist): {e}")
        return {
            "menus": [],
            "count": 0
        }
    except Exception as e:
        logger.error(f"Error listing IVR menus: {e}")
        return {
            "menus": [],
            "count": 0
        }


@router.get("/menus/{menu_id}")
async def get_ivr_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Get IVR menu with all options"""
    try:
        menu = await db.execute(text("""
            SELECT id, name, description, is_default, is_active,
                   greeting_text, greeting_audio_url, timeout_seconds,
                   max_attempts, timeout_action, created_at
            FROM ivr_menus WHERE id = :menu_id
        """), {"menu_id": menu_id}).fetchone()

        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")

        # Get options
        options = await db.execute(text("""
            SELECT id, dtmf_digit, label, action_type, action_target,
                   announcement_text, is_active, display_order
            FROM ivr_menu_options
            WHERE menu_id = :menu_id
            ORDER BY display_order, dtmf_digit
        """), {"menu_id": menu_id}).fetchall()

        return {
            "id": menu.id,
            "name": menu.name,
            "description": menu.description,
            "is_default": menu.is_default,
            "is_active": menu.is_active,
            "greeting_text": menu.greeting_text,
            "greeting_audio_url": menu.greeting_audio_url,
            "timeout_seconds": menu.timeout_seconds,
            "max_attempts": menu.max_attempts,
            "timeout_action": menu.timeout_action,
            "created_at": menu.created_at.isoformat() if menu.created_at else None,
            "options": [
                {
                    "id": opt.id,
                    "dtmf_digit": opt.dtmf_digit,
                    "label": opt.label,
                    "action_type": opt.action_type,
                    "action_target": opt.action_target,
                    "announcement_text": opt.announcement_text,
                    "is_active": opt.is_active,
                    "display_order": opt.display_order
                }
                for opt in options
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting IVR menu: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/menus/{menu_id}")
async def update_ivr_menu(
    menu_id: int,
    menu: IVRMenuUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Update IVR menu"""
    try:
        existing = await db.execute(text(
            "SELECT id FROM ivr_menus WHERE id = :menu_id"
        ), {"menu_id": menu_id}).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Menu not found")

        if menu.is_default:
            await db.execute(text(
                "UPDATE ivr_menus SET is_default = FALSE WHERE is_default = TRUE AND id != :menu_id"
            ), {"menu_id": menu_id})

        updates = []
        params = {"menu_id": menu_id}

        if menu.name is not None:
            updates.append("name = :name")
            params["name"] = menu.name
        if menu.description is not None:
            updates.append("description = :description")
            params["description"] = menu.description
        if menu.is_default is not None:
            updates.append("is_default = :is_default")
            params["is_default"] = menu.is_default
        if menu.is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = menu.is_active
        if menu.greeting_text is not None:
            updates.append("greeting_text = :greeting_text")
            params["greeting_text"] = menu.greeting_text
        if menu.greeting_audio_url is not None:
            updates.append("greeting_audio_url = :greeting_audio_url")
            params["greeting_audio_url"] = menu.greeting_audio_url
        if menu.timeout_seconds is not None:
            updates.append("timeout_seconds = :timeout_seconds")
            params["timeout_seconds"] = menu.timeout_seconds
        if menu.max_attempts is not None:
            updates.append("max_attempts = :max_attempts")
            params["max_attempts"] = menu.max_attempts
        if menu.timeout_action is not None:
            updates.append("timeout_action = :timeout_action")
            params["timeout_action"] = menu.timeout_action

        updates.append("updated_at = CURRENT_TIMESTAMP")

        if updates:
            sql = "UPDATE ivr_menus SET " + ", ".join(updates) + " WHERE id = :menu_id"
            await db.execute(text(sql), params)
            await db.commit()

        return {"success": True, "message": "Menu updated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error updating IVR menu: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/menus/{menu_id}")
async def delete_ivr_menu(
    menu_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Delete (deactivate) IVR menu"""
    try:
        result = await db.execute(text("""
            UPDATE ivr_menus SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :menu_id
        """), {"menu_id": menu_id})

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Menu not found")

        return {"success": True, "message": "Menu deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error deleting IVR menu: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# IVR MENU OPTIONS CRUD
# ============================================================================

@router.post("/menus/{menu_id}/options")
async def create_ivr_option(
    menu_id: int,
    option: IVROptionCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Add an option to an IVR menu"""
    try:
        # Verify menu exists
        menu = await db.execute(text(
            "SELECT id FROM ivr_menus WHERE id = :menu_id"
        ), {"menu_id": menu_id}).fetchone()

        if not menu:
            raise HTTPException(status_code=404, detail="Menu not found")

        # Check for duplicate digit
        existing = await db.execute(text("""
            SELECT id FROM ivr_menu_options
            WHERE menu_id = :menu_id AND dtmf_digit = :digit
        """), {"menu_id": menu_id, "digit": option.dtmf_digit}).fetchone()

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Option for digit '{option.dtmf_digit}' already exists"
            )

        result = await db.execute(text("""
            INSERT INTO ivr_menu_options
            (menu_id, dtmf_digit, label, action_type, action_target,
             announcement_text, display_order, is_active)
            VALUES
            (:menu_id, :digit, :label, :action_type, :action_target,
             :announcement, :display_order, TRUE)
            RETURNING id
        """), {
            "menu_id": menu_id,
            "digit": option.dtmf_digit,
            "label": option.label,
            "action_type": option.action_type.value,
            "action_target": option.action_target,
            "announcement": option.announcement_text,
            "display_order": option.display_order
        })

        try:
            option_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in add_menu_option: {e}")
            option_id = result.lastrowid or await db.execute(text("SELECT last_insert_rowid()")).scalar()

        await db.commit()

        return {
            "success": True,
            "message": f"Option '{option.dtmf_digit}' added",
            "option_id": option_id
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error creating IVR option: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/menus/{menu_id}/options/{option_id}")
async def update_ivr_option(
    menu_id: int,
    option_id: int,
    option: IVROptionUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Update an IVR menu option"""
    try:
        existing = await db.execute(text("""
            SELECT id FROM ivr_menu_options
            WHERE id = :option_id AND menu_id = :menu_id
        """), {"option_id": option_id, "menu_id": menu_id}).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Option not found")

        updates = []
        params = {"option_id": option_id}

        if option.label is not None:
            updates.append("label = :label")
            params["label"] = option.label
        if option.action_type is not None:
            updates.append("action_type = :action_type")
            params["action_type"] = option.action_type.value
        if option.action_target is not None:
            updates.append("action_target = :action_target")
            params["action_target"] = option.action_target
        if option.announcement_text is not None:
            updates.append("announcement_text = :announcement")
            params["announcement"] = option.announcement_text
        if option.is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = option.is_active
        if option.display_order is not None:
            updates.append("display_order = :display_order")
            params["display_order"] = option.display_order

        if updates:
            sql = "UPDATE ivr_menu_options SET " + ", ".join(updates) + " WHERE id = :option_id"
            await db.execute(text(sql), params)
            await db.commit()

        return {"success": True, "message": "Option updated"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error updating IVR option: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/menus/{menu_id}/options/{option_id}")
async def delete_ivr_option(
    menu_id: int,
    option_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Delete an IVR menu option"""
    try:
        result = await db.execute(text("""
            DELETE FROM ivr_menu_options
            WHERE id = :option_id AND menu_id = :menu_id
        """), {"option_id": option_id, "menu_id": menu_id})

        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Option not found")

        return {"success": True, "message": "Option deleted"}

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error deleting IVR option: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# TWIML ENDPOINTS FOR IVR
# ============================================================================

@router.post("/twiml/menu")
@router.get("/twiml/menu")
async def ivr_menu_twiml(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generate TwiML for IVR menu.
    This is the main entry point for IVR calls.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        menu_id = query_params.get("menu_id")
        attempt = int(query_params.get("attempt", "1"))

        # Get menu (default if no ID provided)
        if menu_id:
            menu = await db.execute(text("""
                SELECT id, name, greeting_text, greeting_audio_url,
                       timeout_seconds, max_attempts, timeout_action
                FROM ivr_menus WHERE id = :id AND is_active = TRUE
            """), {"id": menu_id}).fetchone()
        else:
            menu = await db.execute(text("""
                SELECT id, name, greeting_text, greeting_audio_url,
                       timeout_seconds, max_attempts, timeout_action
                FROM ivr_menus WHERE is_default = TRUE AND is_active = TRUE
            """)).fetchone()

        if not menu:
            # No IVR configured - go to AI receptionist
            response = TeXMLResponse()
            response.say("Welcome. Please hold while I connect you.", voice="Polly.Joanna")
            response.redirect("/api/v1/voice/incoming")
            return Response(content=str(response), media_type="application/xml")

        # Get options
        options = await db.execute(text("""
            SELECT dtmf_digit, label, action_type, action_target, announcement_text
            FROM ivr_menu_options
            WHERE menu_id = :menu_id AND is_active = TRUE
            ORDER BY display_order, dtmf_digit
        """), {"menu_id": menu.id}).fetchall()

        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        response = TeXMLResponse()

        # Create gather for DTMF input
        gather = response.gather(
            num_digits=1,
            action=f"{base_url}/api/v1/ivr/twiml/handle-input?menu_id={menu.id}&attempt={attempt}",
            method="POST",
            timeout=menu.timeout_seconds or 10,
            input="dtmf speech"  # Accept both DTMF and speech
        )

        # Play greeting
        if menu.greeting_audio_url:
            gather.play(menu.greeting_audio_url)
        elif menu.greeting_text:
            gather.say(menu.greeting_text, voice="Polly.Joanna")
        else:
            gather.say("Welcome. Please select from the following options.", voice="Polly.Joanna")

        # Read out options
        for opt in options:
            gather.say(f"Press {opt.dtmf_digit} for {opt.label}.", voice="Polly.Joanna")

        # Handle no input (timeout)
        if attempt < (menu.max_attempts or 3):
            response.say("We didn't receive your selection.", voice="Polly.Joanna")
            response.redirect(f"{base_url}/api/v1/ivr/twiml/menu?menu_id={menu.id}&attempt={attempt + 1}")
        else:
            # Max attempts reached - do timeout action
            response.redirect(f"{base_url}/api/v1/ivr/twiml/timeout?menu_id={menu.id}&action={menu.timeout_action}")

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error generating IVR TwiML: {e}")
        response = TeXMLResponse()
        response.say("We're experiencing technical difficulties. Please try again later.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/handle-input")
async def ivr_handle_input_twiml(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle DTMF input from IVR menu.
    Routes to appropriate action based on digit pressed.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        form_data = await request.form()

        menu_id = query_params.get("menu_id")
        attempt = int(query_params.get("attempt", "1"))
        digits = form_data.get("Digits", "")
        speech_result = form_data.get("SpeechResult", "")

        logger.info(f"IVR input received: menu_id={menu_id}, digits={digits}, speech={speech_result}")

        # Handle speech input (convert to digit if possible)
        if not digits and speech_result:
            digits = speech_to_digit(speech_result)

        if not digits:
            # No valid input
            base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
            if base_url and not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            response = TeXMLResponse()
            response.say("Sorry, I didn't understand that selection.", voice="Polly.Joanna")
            response.redirect(f"{base_url}/api/v1/ivr/twiml/menu?menu_id={menu_id}&attempt={attempt + 1}")
            return Response(content=str(response), media_type="application/xml")

        # Look up the option for this digit
        option = await db.execute(text("""
            SELECT dtmf_digit, label, action_type, action_target, announcement_text
            FROM ivr_menu_options
            WHERE menu_id = :menu_id AND dtmf_digit = :digit AND is_active = TRUE
        """), {"menu_id": menu_id, "digit": digits}).fetchone()

        if not option:
            # Invalid option
            base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
            if base_url and not base_url.startswith("http"):
                base_url = f"https://{base_url}"

            response = TeXMLResponse()
            response.say("That is not a valid option. Please try again.", voice="Polly.Joanna")
            response.redirect(f"{base_url}/api/v1/ivr/twiml/menu?menu_id={menu_id}&attempt={attempt + 1}")
            return Response(content=str(response), media_type="application/xml")

        # Execute the action
        return await execute_ivr_action(option, db)

    except Exception as e:
        logger.error(f"Error handling IVR input: {e}")
        response = TeXMLResponse()
        response.say("An error occurred. Please try again later.", voice="Polly.Joanna")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


@router.post("/twiml/timeout")
async def ivr_timeout_twiml(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle IVR timeout after max attempts.
    """
    from telephony.providers.telnyx.texml import TeXMLResponse

    try:
        query_params = request.query_params
        menu_id = query_params.get("menu_id")
        action = query_params.get("action", "transfer_receptionist")

        response = TeXMLResponse()

        if action == "voicemail":
            response.say("Please leave a message after the beep.", voice="Polly.Joanna")
            response.record(
                max_length=120,
                action="/api/v1/voice/voicemail-transcription",
                transcribe=True
            )
        elif action == "transfer_receptionist" or action == "ai_receptionist":
            response.say("Let me connect you with someone who can help.", voice="Polly.Joanna")
            response.redirect("/api/v1/voice/incoming")
        elif action == "hangup":
            response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
            response.hangup()
        else:
            # Default - connect to AI
            response.redirect("/api/v1/voice/incoming")

        return Response(content=str(response), media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in IVR timeout: {e}")
        response = TeXMLResponse()
        response.hangup()
        return Response(content=str(response), media_type="application/xml")


async def execute_ivr_action(option, db: Session):
    """Execute the action for an IVR option"""
    from telephony.providers.telnyx.texml import TeXMLResponse

    response = TeXMLResponse()
    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
    if base_url and not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    action_type = option.action_type
    action_target = option.action_target
    announcement = option.announcement_text

    # Sanitize action_target to prevent path traversal / injection
    import re
    if action_target and not re.match(r'^[\w\-\.]+$', str(action_target)):
        logger.warning(f"Invalid IVR action_target rejected")
        response.say("An error occurred routing your call.", voice="Polly.Joanna")
        return response

    # Play announcement if any
    if announcement:
        response.say(announcement, voice="Polly.Joanna")

    if action_type == "transfer_user":
        # Get user's phone number
        user_phone = db.execute(text("""
            SELECT phone, work_phone, mobile_phone FROM users WHERE id = :user_id
        """), {"user_id": action_target}).fetchone()

        if user_phone:
            phone = user_phone.mobile_phone or user_phone.work_phone or user_phone.phone
            if phone:
                response.say("Connecting you now.", voice="Polly.Joanna")
                dial = response.dial(caller_id=os.getenv("TELNYX_PHONE_NUMBER", ""))
                dial.number(phone)
            else:
                response.say("That extension is not available. Please try again later.", voice="Polly.Joanna")
                response.redirect(f"{base_url}/api/v1/voice/voicemail")
        else:
            response.say("That extension is not available.", voice="Polly.Joanna")
            response.redirect(f"{base_url}/api/v1/voice/voicemail")

    elif action_type == "transfer_phone":
        response.say("Connecting you now.", voice="Polly.Joanna")
        dial = response.dial(caller_id=os.getenv("TELNYX_PHONE_NUMBER", ""))
        dial.number(action_target)

    elif action_type == "transfer_queue":
        response.say("Please hold while we connect you to the next available representative.", voice="Polly.Joanna")
        response.redirect(f"{base_url}/api/v1/queues/twiml/enqueue?queue={action_target}")

    elif action_type == "submenu":
        response.redirect(f"{base_url}/api/v1/ivr/twiml/menu?menu_id={action_target}")

    elif action_type == "voicemail":
        response.say("Please leave a message after the beep.", voice="Polly.Joanna")
        response.record(
            max_length=120,
            action="/api/v1/voice/voicemail-transcription",
            transcribe=True
        )

    elif action_type == "ai_receptionist":
        response.redirect("/api/v1/voice/incoming")

    elif action_type == "play_message":
        response.say(action_target or "Thank you for your inquiry.", voice="Polly.Joanna")
        response.hangup()

    elif action_type == "hangup":
        response.say("Thank you for calling. Goodbye.", voice="Polly.Joanna")
        response.hangup()

    elif action_type == "repeat":
        # Redirect back to menu
        response.redirect(f"{base_url}/api/v1/ivr/twiml/menu")

    else:
        # Unknown action - go to AI
        response.redirect("/api/v1/voice/incoming")

    return Response(content=str(response), media_type="application/xml")


def speech_to_digit(speech: str) -> str:
    """Convert speech recognition result to digit"""
    speech = speech.lower().strip()

    mappings = {
        "one": "1", "1": "1", "won": "1",
        "two": "2", "2": "2", "to": "2", "too": "2",
        "three": "3", "3": "3", "free": "3",
        "four": "4", "4": "4", "for": "4",
        "five": "5", "5": "5",
        "six": "6", "6": "6",
        "seven": "7", "7": "7",
        "eight": "8", "8": "8", "ate": "8",
        "nine": "9", "9": "9",
        "zero": "0", "0": "0", "oh": "0",
        "star": "*", "asterisk": "*",
        "pound": "#", "hash": "#", "number": "#",
    }

    # Try direct mapping
    if speech in mappings:
        return mappings[speech]

    # Try to find a digit word in the speech
    for word, digit in mappings.items():
        if word in speech:
            return digit

    return ""


# ============================================================================
# PREDEFINED IVR TEMPLATES
# ============================================================================

@router.get("/templates")
async def list_ivr_templates():
    """Get predefined IVR menu templates"""
    templates = [
        {
            "id": "mortgage_basic",
            "name": "Basic Mortgage IVR",
            "description": "Simple menu for mortgage inquiries",
            "greeting": "Thank you for calling. For new loan inquiries, press 1. For existing loan status, press 2. To speak with a representative, press 0.",
            "options": [
                {"digit": "1", "label": "New Loan Inquiries", "action": "transfer_queue", "target": "sales"},
                {"digit": "2", "label": "Existing Loan Status", "action": "transfer_queue", "target": "support"},
                {"digit": "0", "label": "Speak to Representative", "action": "ai_receptionist"},
            ]
        },
        {
            "id": "mortgage_full",
            "name": "Full Mortgage IVR",
            "description": "Comprehensive menu for mortgage company",
            "greeting": "Welcome to our mortgage services. Please listen carefully to the following options.",
            "options": [
                {"digit": "1", "label": "Get a Rate Quote", "action": "ai_receptionist"},
                {"digit": "2", "label": "Apply for a Loan", "action": "transfer_queue", "target": "sales"},
                {"digit": "3", "label": "Existing Loan Status", "action": "transfer_queue", "target": "support"},
                {"digit": "4", "label": "Make a Payment", "action": "play_message", "target": "To make a payment, please visit our website or call our payment line."},
                {"digit": "5", "label": "Document Upload Status", "action": "transfer_queue", "target": "processing"},
                {"digit": "0", "label": "Speak to Representative", "action": "ai_receptionist"},
            ]
        },
        {
            "id": "after_hours",
            "name": "After Hours IVR",
            "description": "Menu for after business hours",
            "greeting": "Thank you for calling. Our office is currently closed. Our business hours are Monday through Friday, 9 AM to 5 PM.",
            "options": [
                {"digit": "1", "label": "Leave a Voicemail", "action": "voicemail"},
                {"digit": "2", "label": "Emergency Assistance", "action": "transfer_phone", "target": "+15551234567"},
                {"digit": "3", "label": "Visit Website", "action": "play_message", "target": "For 24/7 access, please visit our website at w w w dot company dot com."},
            ]
        }
    ]

    return {"templates": templates}


@router.post("/templates/{template_id}/apply")
async def apply_ivr_template(
    template_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user_optional)
):
    """Apply a predefined template to create an IVR menu"""
    try:
        # Get template
        templates_response = await list_ivr_templates()
        templates = templates_response["templates"]
        template = next((t for t in templates if t["id"] == template_id), None)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Create menu
        result = await db.execute(text("""
            INSERT INTO ivr_menus
            (name, description, greeting_text, timeout_action, is_active, created_by)
            VALUES
            (:name, :description, :greeting, :timeout_action, TRUE, :created_by)
            RETURNING id
        """), {
            "name": template["name"],
            "description": template["description"],
            "greeting": template["greeting"],
            "timeout_action": "ai_receptionist",
            "created_by": current_user.id if current_user else None
        })

        try:
            menu_id = result.fetchone()[0]
        except Exception as e:
            logger.error(f"Error fetching RETURNING id in create_template_menu: {e}")
            menu_id = result.lastrowid or await db.execute(text("SELECT last_insert_rowid()")).scalar()

        # Create options
        for idx, opt in enumerate(template["options"]):
            await db.execute(text("""
                INSERT INTO ivr_menu_options
                (menu_id, dtmf_digit, label, action_type, action_target, display_order, is_active)
                VALUES
                (:menu_id, :digit, :label, :action, :target, :order, TRUE)
            """), {
                "menu_id": menu_id,
                "digit": opt["digit"],
                "label": opt["label"],
                "action": opt["action"],
                "target": opt.get("target"),
                "order": idx
            })

        await db.commit()

        return {
            "success": True,
            "message": f"Template '{template['name']}' applied",
            "menu_id": menu_id
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Error applying template: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
