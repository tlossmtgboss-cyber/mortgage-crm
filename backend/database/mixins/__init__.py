"""
Database mixins for cross-cutting concerns.

Modules:
  - soft_delete: SoftDeleteMixin for compliance-safe record retention
"""

from database.mixins.soft_delete import SoftDeleteMixin

__all__ = ["SoftDeleteMixin"]
