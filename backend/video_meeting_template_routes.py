"""
UVIP - Video Meeting Template Routes
Extracted from video_meeting_routes.py

Handles:
- Meeting template CRUD (list, create, update, delete)
- Seed default templates
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
import logging

from video_meeting_models import DEFAULT_MEETING_TEMPLATES
from video_meeting_shared import get_db, get_current_user, get_models
from video_meeting_schemas import MeetingTemplateCreate, MeetingTemplateUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# TEMPLATE ENDPOINTS
# ============================================================================

@router.get("/templates")
async def list_templates(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """List all meeting templates."""
    _models = get_models()
    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        return {"templates": DEFAULT_MEETING_TEMPLATES}

    templates = db.query(MeetingTemplate).filter(
        or_(
            MeetingTemplate.is_system_template == True,
            MeetingTemplate.organization_id == getattr(current_user, 'organization_id', None)
        ),
        MeetingTemplate.is_active == True
    ).all()

    return {
        "templates": [
            {
                "id": t.id,
                "template_key": t.template_key,
                "template_name": t.template_name,
                "description": t.description,
                "default_duration_minutes": t.default_duration_minutes,
                "recording_enabled": t.recording_enabled,
                "ai_assistant_enabled": t.ai_assistant_enabled,
                "default_agenda": t.default_agenda,
                "color": t.color,
                "icon": t.icon,
                "is_system_template": t.is_system_template
            }
            for t in templates
        ]
    }


@router.post("/templates")
async def create_template(
    data: MeetingTemplateCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a new meeting template."""
    _models = get_models()
    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    template = MeetingTemplate(
        template_name=data.template_name,
        template_key=data.template_key,
        description=data.description,
        organization_id=getattr(current_user, 'organization_id', None),
        is_system_template=False,
        default_duration_minutes=data.default_duration_minutes,
        waiting_room_enabled=data.waiting_room_enabled,
        recording_enabled=data.recording_enabled,
        transcription_enabled=data.transcription_enabled,
        ai_assistant_enabled=data.ai_assistant_enabled,
        default_agenda=data.default_agenda or [],
        color=data.color,
        icon=data.icon,
        created_by=current_user.id
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return {"success": True, "template": {"id": template.id, "template_key": template.template_key}}


@router.post("/templates/seed-defaults")
async def seed_default_templates(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Seed default meeting templates."""
    _models = get_models()
    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    created = 0
    for template_data in DEFAULT_MEETING_TEMPLATES:
        existing = db.query(MeetingTemplate).filter(
            MeetingTemplate.template_key == template_data['template_key']
        ).first()

        if not existing:
            template = MeetingTemplate(
                template_key=template_data['template_key'],
                template_name=template_data['template_name'],
                description=template_data['description'],
                default_duration_minutes=template_data['default_duration_minutes'],
                recording_enabled=template_data['recording_enabled'],
                ai_assistant_enabled=template_data['ai_assistant_enabled'],
                default_agenda=template_data['default_agenda'],
                color=template_data['color'],
                icon=template_data['icon'],
                is_system_template=True,
                is_active=True
            )
            db.add(template)
            created += 1

    db.commit()

    return {"success": True, "message": f"Seeded {created} default templates"}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    data: MeetingTemplateUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update an existing meeting template."""
    _models = get_models()
    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field not in _protected and hasattr(template, field):
            setattr(template, field, value)

    db.commit()
    db.refresh(template)

    return {
        "success": True,
        "template": {
            "id": template.id,
            "template_key": template.template_key,
            "template_name": template.template_name,
            "description": template.description,
            "default_duration_minutes": template.default_duration_minutes,
            "recording_enabled": template.recording_enabled,
            "ai_assistant_enabled": template.ai_assistant_enabled,
            "color": template.color,
            "icon": template.icon
        }
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Delete a meeting template."""
    _models = get_models()
    MeetingTemplate = _models.get('MeetingTemplate')
    if MeetingTemplate is None:
        raise HTTPException(status_code=500, detail="MeetingTemplate model not found")

    template = db.query(MeetingTemplate).filter(MeetingTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.is_system_template:
        raise HTTPException(status_code=400, detail="Cannot delete system templates")

    db.delete(template)
    db.commit()

    return {"success": True, "message": "Template deleted"}
