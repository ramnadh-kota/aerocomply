from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_db_session

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness() -> dict:
    """Liveness probe: process is up. No dependency checks."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db_session)) -> dict:
    """Readiness probe: verifies the database connection is usable."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
