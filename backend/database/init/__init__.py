"""
Database Initialization Sub-modules

Decomposed from database/init_db.py into focused modules:
    schema.py             - CREATE TABLE statements for standalone tables
    migrations.py         - ALTER TABLE column additions, enum updates, data fixups
    indexes.py            - CREATE INDEX statements
    seeds.py              - Sample/demo data and holiday seed data
    external_migrations.py - Calls to external migration scripts in migrations/

Usage (unchanged from init_db.py):
    from database.init_db import init_module, init_db, create_sample_data
"""

from .schema import run_schema_creation
from .migrations import run_column_migrations
from .indexes import run_index_creation
from .seeds import create_sample_data, seed_holidays
from .external_migrations import run_external_migrations
