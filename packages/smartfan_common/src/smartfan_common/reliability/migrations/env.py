"""Programmatic migrations share the caller's administrative transaction."""

from alembic import context

connection = context.config.attributes["connection"]
context.configure(connection=connection, version_table_schema="transport")
with context.begin_transaction():
    context.run_migrations()
