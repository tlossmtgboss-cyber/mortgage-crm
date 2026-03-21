"""
Scheduler dependency injection core — shared state used by all helper sub-modules.

This module holds the mutable DI storage that gets populated at startup
via set_dependencies() / set_enhanced_dependencies() from the parent
scheduler __init__.py or main.py.
"""

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None
_enhanced_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set core dependencies from parent module."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


def set_enhanced_dependencies(get_db_func, get_current_user_func, models_dict, enhanced_models_dict):
    """Set dependencies for enhanced scheduler features (resources, soft holds, SLA, etc.)."""
    global _get_db, _get_current_user_func, _models, _enhanced_models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _enhanced_models = enhanced_models_dict


def get_models():
    """Get models dict (for use by sub-modules)."""
    return _models


def get_enhanced_models():
    """Get enhanced models dict."""
    return _enhanced_models


def get_current_user_func():
    """Get the current user auth function (for use by _auth.py)."""
    return _get_current_user_func
