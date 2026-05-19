"""
Inline legacy routes sub-modules.

This package contains route groups extracted from the monolithic
`backend/routes/inline_legacy_routes.py` file. Each module exposes a
`register_<group>(app, deps)` function called by `register_inline_routes`.

Sub-modules are purely mechanical extractions — they MUST NOT change route
paths, response shapes, or function bodies. The orchestrator owns dependency
wiring and collects exported functions from each sub-module.
"""
