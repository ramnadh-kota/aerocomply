from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    # Without an explicit connect_timeout, a genuinely unreachable database
    # (the exact scenario /health/ready exists to detect) hangs for the
    # platform's default TCP timeout — tens of seconds, not the few-second
    # window most orchestrators allow a readiness probe. This bounds new
    # connection attempts; pool_pre_ping above handles stale/dropped
    # connections already in the pool.
    connect_args={"connect_timeout": 5},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
