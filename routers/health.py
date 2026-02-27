import os

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool, text
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@router.get("/health/deep", tags=["meta"])
def health_deep():
    db_status = "unknown"
    pending = -1

    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        return {"status": "degraded", "db": "no DATABASE_URL configured", "pending_migrations": pending}

    # Strip ?options= query param; set search_path via connect_args to avoid configparser % issue.
    clean_url = raw_url.split("?")[0] if "?" in raw_url else raw_url

    try:
        engine = create_engine(
            clean_url,
            poolclass=pool.NullPool,
            connect_args={"options": "-csearch_path=hr"},
        )
        with engine.connect() as sa_conn:
            sa_conn.execute(text("SELECT 1"))
            db_status = "connected"

            try:
                alembic_cfg = Config("alembic.ini")
                script = ScriptDirectory.from_config(alembic_cfg)
                migration_ctx = MigrationContext.configure(sa_conn)
                current = migration_ctx.get_current_revision()
                head = script.get_current_head()
                pending = 0 if current == head else 1
            except Exception:
                pending = -1
    except Exception as e:
        return {"status": "degraded", "db": "error", "error": str(e)}

    return {"status": "ok", "db": db_status, "pending_migrations": pending}
