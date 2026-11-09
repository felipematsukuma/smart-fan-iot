"""Privileged one-shot role provisioning; secrets never enter runtime roles."""

import re
from pathlib import Path

from smartfan_common.reliability.database import ROLES, migrate
from sqlalchemy import Engine, text


def provision_database(
    engine: Engine, secret_directory: Path, database: str = "smartfan"
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("Invalid database identifier")
    with engine.begin() as conn:
        conn.execute(text(f'REVOKE ALL ON DATABASE "{database}" FROM PUBLIC'))
        conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
        for role in ROLES:
            username = "smartfan_" + role
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname=:name"), {"name": username}
            ).first()
            if exists is None:
                password = (secret_directory / ("postgres_" + role)).read_text().strip()
                if len(password) < 32:
                    raise ValueError("Invalid service credential file")
                conn.execute(
                    text(
                        f'CREATE ROLE "{username}" LOGIN PASSWORD :password NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
                    ),
                    {"password": password},
                )
            conn.execute(
                text(f'GRANT CONNECT ON DATABASE "{database}" TO "{username}"')
            )
    migrate(engine)
