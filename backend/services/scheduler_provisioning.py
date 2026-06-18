"""
Scheduler Provisioning Service
Enterprise Readiness - Domain 5

Auto-provisions a SchedulerConfig + default AppointmentType records for newly
created users (SCIM, JIT SSO, CSV bulk import).

Design principles:
  - Idempotent: safe to call even if a config already exists (no-op).
  - Never raises: swallows all exceptions with logger.warning so that a
    scheduler provisioning failure never blocks user creation.
  - Synchronous: called inline after user INSERT; no task queue required.
"""

import logging
from typing import Union

logger = logging.getLogger(__name__)


async def auto_provision_scheduler_config(
    user_id: Union[int, str],
    organization_id: Union[int, str],
    db,
    user_email: str = "",
) -> None:
    """
    Create a default SchedulerConfig + seed 7 default AppointmentType records
    for a newly provisioned user.

    Called after user creation in:
      - JIT SSO provisioning (auth/jit_provisioning.py)
      - SCIM 2.0 POST /scim/v2/Users
      - CSV bulk import /api/v1/admin/users/import-csv

    Args:
        user_id:         ID of the newly created user.
        organization_id: ID of the user's organization.
        db:              SQLAlchemy Session.
        user_email:      Optional email used for config_name; falls back to
                         "user_{user_id}".

    Returns:
        None.  Exceptions are swallowed so caller is never disrupted.
    """
    try:
        user_id = int(user_id)
        organization_id = int(organization_id)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "auto_provision_scheduler_config: invalid user_id=%r or org_id=%r — %s",
            user_id, organization_id, exc,
        )
        return

    try:
        # ------------------------------------------------------------------ #
        # 1. Import models (lazy to avoid circular imports at module load)     #
        # ------------------------------------------------------------------ #
        from database.models.scheduler import SchedulerConfig, SchedulerAppointmentType
        from smart_scheduler_models import DEFAULT_APPOINTMENT_TYPES, DEFAULT_WORKING_HOURS

        # ------------------------------------------------------------------ #
        # 2. Idempotency check — bail out if config already exists             #
        # ------------------------------------------------------------------ #
        existing = (
            db.query(SchedulerConfig)
            .filter(
                SchedulerConfig.user_id == user_id,
                SchedulerConfig.organization_id == organization_id,
            )
            .first()
        )

        if existing:
            logger.debug(
                "auto_provision_scheduler_config: config already exists for "
                "user_id=%d org_id=%d (config_id=%d) — skipping",
                user_id, organization_id, existing.id,
            )
            return

        # ------------------------------------------------------------------ #
        # 3. Create SchedulerConfig with sensible defaults                     #
        # ------------------------------------------------------------------ #
        config_name = (
            f"{user_email}'s Schedule"
            if user_email
            else f"user_{user_id}'s Schedule"
        )

        config = SchedulerConfig(
            user_id=user_id,
            organization_id=organization_id,
            config_name=config_name,
            description="Auto-provisioned calendar configuration",
            timezone="America/New_York",  # Eastern — matches project preference
            default_duration_minutes=30,
            min_duration_minutes=15,
            max_duration_minutes=120,
            buffer_before_minutes=5,
            buffer_after_minutes=5,
            min_notice_hours=2,
            max_advance_days=60,
            max_meetings_per_day=8,
            max_consecutive_meetings=3,
            enforce_lunch_break=True,
            working_hours=DEFAULT_WORKING_HOURS,
            preferred_meeting_modes=["video", "phone"],
            zoom_enabled=True,
            google_meet_enabled=True,
            auto_create_meeting_link=True,
            ai_scheduling_enabled=True,
            ai_can_reschedule=True,
            ai_can_cancel=False,
            auto_reschedule_enabled=True,
            smart_reminders_enabled=True,
            setup_completed=False,
            is_active=True,
        )

        db.add(config)
        db.flush()  # Assign config.id without committing — lets caller manage tx

        # ------------------------------------------------------------------ #
        # 4. Seed the 7 default AppointmentType records                        #
        # ------------------------------------------------------------------ #
        created_count = 0
        for idx, apt_def in enumerate(DEFAULT_APPOINTMENT_TYPES):
            appt_type = SchedulerAppointmentType(
                config_id=config.id,
                organization_id=organization_id,
                type_key=apt_def["type_key"],
                type_name=apt_def["type_name"],
                description=apt_def.get("description", ""),
                meeting_type=apt_def["meeting_type"],
                default_duration_minutes=apt_def["default_duration_minutes"],
                allowed_durations=apt_def.get("allowed_durations", [15, 30, 45, 60]),
                requires_loan_id=apt_def.get("requires_loan_id", False),
                requires_lead_id=apt_def.get("requires_lead_id", False),
                requires_contact_info=True,
                intake_questions=apt_def.get("intake_questions", []),
                color=apt_def.get("color", "#3b82f6"),
                icon=apt_def.get("icon", "calendar"),
                is_public=True,
                # Scoped slug: user_id-type_key guarantees uniqueness across org
                public_slug=f"{user_id}-{apt_def['type_key']}",
                display_order=idx,
                is_active=True,
            )
            db.add(appt_type)
            created_count += 1

        db.commit()

        logger.info(
            "auto_provision_scheduler_config: provisioned config_id=%d with "
            "%d appointment types for user_id=%d org_id=%d",
            config.id, created_count, user_id, organization_id,
        )

    except Exception as exc:  # noqa: BLE001
        # Never let provisioning failure block user creation
        logger.warning(
            "auto_provision_scheduler_config: failed for user_id=%r org_id=%r — %s",
            user_id, organization_id, exc,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
