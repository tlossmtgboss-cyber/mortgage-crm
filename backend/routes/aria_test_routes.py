"""
Serves the standalone Aria test page.

Accessible at /aria-test (on the backend API).
Bypasses the frontend SPA routing entirely.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse


_HTML_CACHE: str | None = None


def _load_html() -> str:
    global _HTML_CACHE
    if _HTML_CACHE is None:
        html_path = Path(__file__).parent / "aria_test_page.html"
        _HTML_CACHE = html_path.read_text(encoding="utf-8")
    return _HTML_CACHE


def register_aria_test_routes(app: FastAPI, **_kwargs):
    @app.get("/aria-test", response_class=HTMLResponse, include_in_schema=False)
    async def aria_test_page():
        return HTMLResponse(content=_load_html())
