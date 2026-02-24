# SOC 2 compliance tables are defined in migrations/soc2_tables.sql
# and accessed via raw SQL (sqlalchemy.text) in the service layer.
# No ORM models are used — all queries go through the service classes.
