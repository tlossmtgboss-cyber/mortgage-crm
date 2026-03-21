"""
Pagination utilities — enforce maximum page sizes to prevent resource exhaustion.

Usage:
    from utils.pagination import clamp_pagination

    @router.get("/items")
    async def list_items(limit: int = 50, offset: int = 0):
        limit, offset = clamp_pagination(limit, offset)
        ...
"""

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50


def clamp_pagination(limit: int = DEFAULT_PAGE_SIZE, offset: int = 0) -> tuple:
    """Enforce pagination limits to prevent resource exhaustion.

    Args:
        limit: Requested page size (clamped to [1, MAX_PAGE_SIZE]).
        offset: Requested offset (clamped to >= 0).

    Returns:
        Tuple of (limit, offset) with safe values.
    """
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    return limit, offset
