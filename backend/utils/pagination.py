"""
Pagination utilities — offset-based clamping and cursor-based pagination.

Usage:
    # Offset-based (existing)
    from utils.pagination import clamp_pagination

    @router.get("/items")
    async def list_items(limit: int = 50, offset: int = 0):
        limit, offset = clamp_pagination(limit, offset)
        ...

    # Cursor-based (v2 API)
    from utils.pagination import paginate_cursor, CursorPage

    @router.get("/v2/leads")
    async def list_leads(cursor: str = None, limit: int = 25):
        query = db.query(Lead).filter(Lead.organization_id == org_id)
        page = paginate_cursor(query, cursor=cursor, limit=limit, order_column=Lead.id)
        return page
"""

import base64
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Query

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50
MAX_CURSOR_PAGE_SIZE = 100
DEFAULT_CURSOR_PAGE_SIZE = 25


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


# ---------------------------------------------------------------------------
# Cursor-based pagination for v2 API
# ---------------------------------------------------------------------------

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """A page of results with an opaque cursor for fetching the next page."""
    items: List[T]
    next_cursor: Optional[str] = None
    has_more: bool
    total_count: Optional[int] = None


def _encode_cursor(value: int) -> str:
    """Encode an integer ID as a URL-safe base64 cursor string."""
    return base64.urlsafe_b64encode(str(value).encode()).decode()


def _decode_cursor(cursor: str) -> int:
    """Decode a base64 cursor string back to an integer ID.

    Raises ValueError if the cursor is malformed.
    """
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        return int(decoded)
    except Exception:
        raise ValueError(f"Invalid cursor: {cursor!r}")


def paginate_cursor(
    query: Query,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_CURSOR_PAGE_SIZE,
    order_column=None,
    include_total: bool = False,
) -> CursorPage:
    """Apply cursor-based pagination to a SQLAlchemy query.

    Args:
        query: A SQLAlchemy Query object (filters already applied).
        cursor: Opaque cursor string from a previous CursorPage.next_cursor.
                None for the first page.
        limit: Maximum items per page (clamped to [1, MAX_CURSOR_PAGE_SIZE]).
        order_column: The SQLAlchemy column to order and cursor by.
                      Must be a unique, sortable column (typically Model.id).
                      If None, defaults to the primary key of the queried entity.
        include_total: If True, run a COUNT query and include total_count.
                       Adds a DB round-trip — use only when needed.

    Returns:
        CursorPage with items, next_cursor, has_more, and optionally total_count.

    Raises:
        ValueError: If cursor is malformed or order_column cannot be determined.
    """
    # Clamp limit
    limit = max(1, min(limit, MAX_CURSOR_PAGE_SIZE))

    # Resolve order column from query entity if not provided
    if order_column is None:
        col_desc = query.column_descriptions
        if col_desc:
            entity = col_desc[0].get("entity")
            if entity is not None and hasattr(entity, "id"):
                order_column = entity.id
        if order_column is None:
            raise ValueError(
                "order_column is required when the query entity "
                "does not have a standard 'id' column"
            )

    # Optional total count
    total_count = None
    if include_total:
        total_count = query.count()

    # Apply cursor filter
    if cursor is not None:
        cursor_value = _decode_cursor(cursor)
        query = query.filter(order_column > cursor_value)

    # Order and fetch limit+1 to detect has_more
    rows = query.order_by(order_column.asc()).limit(limit + 1).all()

    has_more = len(rows) > limit
    items = rows[:limit]

    # Build next cursor from the last item's order column value
    next_cursor = None
    if has_more and items:
        last_item = items[-1]
        # order_column.key gives the attribute name on the model (e.g. "id")
        col_key = order_column.key
        last_value = getattr(last_item, col_key)
        next_cursor = _encode_cursor(int(last_value))

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )
