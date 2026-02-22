"""
Canonical auth dependencies for FastAPI route files.

All route files should import auth dependencies from here instead of
redefining their own get_current_user / get_current_user_flexible.

Usage:
    from auth.dependencies import get_current_user, get_current_user_flexible, oauth2_scheme

    @router.get("/my-endpoint")
    async def my_endpoint(user = Depends(get_current_user)):
        ...

NOTE: Uses lazy imports from main to avoid circular import at module load time.
The functions themselves are resolved at request time (FastAPI dependency injection).
"""
import logging

logger = logging.getLogger(__name__)


def _get_main_auth():
    """Lazy import auth functions from main.py to avoid circular imports."""
    from main import (
        get_current_user,
        get_current_user_flexible,
        oauth2_scheme,
    )
    return get_current_user, get_current_user_flexible, oauth2_scheme


def get_current_user():
    """FastAPI dependency — returns the canonical get_current_user from main.py.

    Usage in routes:
        @router.get("/endpoint")
        async def handler(user = Depends(get_current_user())):
            ...

    Or use the Depends-compatible reference directly:
        from auth.dependencies import current_user_dep
        @router.get("/endpoint")
        async def handler(user = Depends(current_user_dep)):
            ...
    """
    gcu, _, _ = _get_main_auth()
    return gcu


def get_current_user_flexible():
    """FastAPI dependency — returns the canonical get_current_user_flexible from main.py."""
    _, gcuf, _ = _get_main_auth()
    return gcuf


def get_oauth2_scheme():
    """Return the canonical oauth2_scheme from main.py."""
    _, _, scheme = _get_main_auth()
    return scheme


# For direct Depends() usage without calling the function:
#   from auth.dependencies import current_user_dep
#   async def handler(user = Depends(current_user_dep)):
#
# These are properties that resolve at import time of the ROUTE module,
# but since routes are imported after main.py is loaded, this is safe.

class _LazyAuthProxy:
    """Proxy that lazily resolves auth dependencies on first access.

    This avoids circular imports while still allowing route files to do:
        from auth.dependencies import current_user_dep
        @router.get("/x")
        async def handler(user = Depends(current_user_dep)): ...
    """

    def __init__(self, attr_name):
        self._attr_name = attr_name
        self._resolved = None

    def _resolve(self):
        if self._resolved is None:
            gcu, gcuf, scheme = _get_main_auth()
            _resolved_map = {
                'get_current_user': gcu,
                'get_current_user_flexible': gcuf,
                'oauth2_scheme': scheme,
            }
            self._resolved = _resolved_map[self._attr_name]
        return self._resolved

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)

    def __repr__(self):
        return f"<LazyAuthProxy({self._attr_name})>"


# Lazy proxies that resolve on first call (compatible with Depends())
current_user_dep = _LazyAuthProxy('get_current_user')
current_user_flexible_dep = _LazyAuthProxy('get_current_user_flexible')
oauth2_scheme = _LazyAuthProxy('oauth2_scheme')


__all__ = [
    'get_current_user',
    'get_current_user_flexible',
    'get_oauth2_scheme',
    'current_user_dep',
    'current_user_flexible_dep',
    'oauth2_scheme',
]
