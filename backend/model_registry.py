"""Single source of truth for registering every ORM model on the canonical Base.

Call register_all_models() exactly once at app startup (main.py) and in test
setup (conftest) BEFORE configure_mappers(). Importing the direct-model modules
self-registers their classes; the factory functions register theirs on the
canonical Base. All string-based relationship() refs resolve once every model
is registered, regardless of call order.
"""
from __future__ import annotations
import importlib
import logging

logger = logging.getLogger(__name__)

# Direct-model modules that self-register on import.
_DIRECT_MODEL_MODULES = [
    "database.models",            # canonical Lead/Loan/User/permission(Role)/etc.
    "models.smart_docs_models",
    "models.sms_models",
]

# Factory modules (def create_*_models(Base)). Order is not load-bearing for
# string-ref resolution (that happens at configure_mappers time), but we list
# them in rough dependency order for readability.
_FACTORY_CALLS = [
    ("user_onboarding_integration", "create_user_onboarding_models"),
    ("models.workflow_sla", "create_workflow_sla_models"),
    ("workflow_config_models", "create_workflow_config_models"),
    ("models.feature_flags", "create_feature_models"),
    ("models.esign_models", "create_esign_models"),
    ("models.perennia_docs", "create_perennia_docs_models"),
    ("smart_scheduler_models", "create_smart_scheduler_models"),
    ("video_clip_models", "create_video_clip_models"),
    ("video_meeting_models", "create_video_meeting_models"),
    ("scheduler_enhancements", "create_scheduler_enhancement_models"),
    ("services.holiday_service", "create_holiday_models"),
]

_registered = False


def register_all_models(Base=None):
    """Idempotent: import all direct models, then call every factory on Base."""
    global _registered
    if Base is None:
        from db import Base as _B
        Base = _B
    for mod in _DIRECT_MODEL_MODULES:
        importlib.import_module(mod)
    for mod_name, fn_name in _FACTORY_CALLS:
        try:
            mod = importlib.import_module(mod_name)
            getattr(mod, fn_name)(Base)
        except Exception as e:
            logger.error("Factory %s.%s failed: %s", mod_name, fn_name, e)
            raise
    _registered = True
    return True


def assert_mappers_configure():
    """Register everything and force mapper configuration (raises on failure)."""
    from sqlalchemy.orm import configure_mappers
    register_all_models()
    configure_mappers()
