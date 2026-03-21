"""
Scheduler dependency injection core — shared state used by all helper sub-modules.

This module holds the mutable DI storage that gets populated at startup
via set_dependencies() / set_enhanced_dependencies() from the parent
scheduler __init__.py or main.py.

The get_*() accessors also check for test monkey-patches on the re-export
modules (_helpers.py, scheduler_appointment_routes.py) so that tests using
``sar._models = {...}`` continue to work after the _helpers decomposition.
"""

import sys
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None
_enhanced_models = None

_UNSET = object()  # sentinel for "not overridden"

# Modules where tests may monkey-patch _models / _get_current_user_func
_OVERRIDE_MODULES = (
    'routes.scheduler._helpers',
    'routes.scheduler_appointment_routes',
)


def _check_override(attr_name):
    """Check if a test has monkey-patched *attr_name* on a re-export module."""
    for mod_name in _OVERRIDE_MODULES:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            val = mod.__dict__.get(attr_name, _UNSET)
            if val is not _UNSET:
                return val
    return _UNSET


def _clear_overrides():
    """Remove stale test monkey-patches so fresh set_dependencies() values take effect."""
    for mod_name in _OVERRIDE_MODULES:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            for attr in ('_models', '_enhanced_models', '_get_db', '_get_current_user_func'):
                mod.__dict__.pop(attr, None)


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set core dependencies from parent module."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _clear_overrides()


def set_enhanced_dependencies(get_db_func, get_current_user_func, models_dict, enhanced_models_dict):
    """Set dependencies for enhanced scheduler features (resources, soft holds, SLA, etc.)."""
    global _get_db, _get_current_user_func, _models, _enhanced_models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _enhanced_models = enhanced_models_dict
    _clear_overrides()


def get_models():
    """Get models dict (for use by sub-modules)."""
    override = _check_override('_models')
    if override is not _UNSET:
        return override
    return _models


def get_enhanced_models():
    """Get enhanced models dict."""
    override = _check_override('_enhanced_models')
    if override is not _UNSET:
        return override
    return _enhanced_models


def get_current_user_func():
    """Get the current user auth function (for use by _auth.py)."""
    override = _check_override('_get_current_user_func')
    if override is not _UNSET:
        return override
    return _get_current_user_func
