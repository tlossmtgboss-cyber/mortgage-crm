"""Per-Base memoization for model factory functions.

Many model factories (`create_*_models(Base)`) are called from several places
(route registration AND model_registry). Without memoization, each call
re-defines the same SQLAlchemy classes/tables on the same Base, which raises
"Table 'x' is already defined" or registers duplicate mappers. Applying
``@base_memoize`` makes a factory idempotent per Base: repeated calls with the
same Base return the identical class dict.
"""
from __future__ import annotations

import functools


def base_memoize(fn):
    """Memoize a ``create_*_models(Base)`` factory keyed by ``id(Base)``."""
    cache = {}

    @functools.wraps(fn)
    def wrapper(Base=None):
        key = id(Base)
        if key not in cache:
            cache[key] = fn(Base)
        return cache[key]

    wrapper._base_cache = cache  # exposed for tests/inspection
    return wrapper
