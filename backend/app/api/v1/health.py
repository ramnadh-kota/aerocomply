from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_db_session

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness() -> dict:
    """Liveness probe: process is up. No dependency checks."""
    return {"status": "ok"}


@lru_cache(maxsize=1)
def expected_schema_heads() -> tuple[str, ...] | None:
    """Alembic head revision(s) this build was released with, or None when the migration scripts are not shipped."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = Path(__file__).resolve().parents[3]
        if not (root / "alembic").is_dir():
            return None
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "alembic"))
        return tuple(sorted(ScriptDirectory.from_config(cfg).get_heads()))
    except Exception:  # noqa: BLE001 - readiness must not fail because of packaging
        return None


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db_session)):
    """Readiness probe. 200 only when the database answers AND its schema is at this build's Alembic head (a new
    image rolled out before `alembic upgrade head` must not receive traffic). Also reports background-job health for
    operators; a growing dead-letter queue or an old queued job does not make the API unready, but is visible here."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unreachable"})

    body: dict = {"status": "ok", "database": "reachable"}
    heads = expected_schema_heads()
    try:
        current = tuple(sorted(r[0] for r in db.execute(text("SELECT version_num FROM alembic_version"))))
    except Exception:  # noqa: BLE001 - no alembic table: schema unmanaged/unknown
        db.rollback()
        current = None
    if heads is not None:
        up_to_date = current == heads
        body["schema"] = {"current": list(current) if current else None, "expected": list(heads), "up_to_date": up_to_date}
        if not up_to_date:
            body["status"] = "schema_mismatch"
            return JSONResponse(status_code=503, content=body)
    try:
        row = db.execute(text(
            "SELECT count(*) FILTER (WHERE status='QUEUED'), count(*) FILTER (WHERE status='DEAD'), "
            "COALESCE(EXTRACT(EPOCH FROM (now() - min(run_after) FILTER (WHERE status='QUEUED' AND run_after <= now()))), 0) "
            "FROM background_jobs")).one()
        body["jobs"] = {"queued": int(row[0]), "dead": int(row[1]), "oldest_due_seconds": round(float(row[2]), 1)}
    except Exception:  # noqa: BLE001 - table absent on an old schema; the schema check above already reports that
        db.rollback()
    return body
