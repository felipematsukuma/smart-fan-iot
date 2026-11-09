"""Explicit connections and Alembic migrations, without legacy configuration."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, text

ROLES = ("gateway", "writer", "inference", "control", "api", "jobs-worker")


def engine_for(
    owner: str,
    password_file: Path,
    *,
    host: str = "postgres",
    database: str = "smartfan",
    port: int = 5432,
) -> Engine:
    if owner not in (*ROLES, "bootstrap"):
        raise ValueError("Unknown service owner")
    password = password_file.read_text(encoding="utf-8").strip()
    if len(password) < 32:
        raise ValueError("Invalid database credential file")
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username="smartfan_" + owner,
            password=password,
            host=host,
            port=port,
            database=database,
        ),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=0,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=5000 -c lock_timeout=3000",
        },
    )


def migrate(engine: Engine) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(734113, 0)"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS transport"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
