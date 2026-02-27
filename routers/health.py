import os

import psycopg2
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@router.get("/health/deep", tags=["meta"])
def health_deep():
    db_status = "unknown"
    pending = -1

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        return {"status": "degraded", "db": "no DATABASE_URL configured", "pending_migrations": pending}

    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        db_status = "connected"

        try:
            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            migration_ctx = MigrationContext.configure(conn)
            current = migration_ctx.get_current_revision()
            head = script.get_current_head()
            pending = 0 if current == head else 1
        except Exception:
            pending = -1
        finally:
            conn.close()
    except Exception as e:
        return {"status": "degraded", "db": "error", "error": str(e)}

    return {"status": "ok", "db": db_status, "pending_migrations": pending}
