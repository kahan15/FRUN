from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import settings


@lru_cache
def engine():
    cfg = settings()
    result = create_engine(
        cfg.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=cfg.db_pool_timeout_seconds,
        hide_parameters=True,
        connect_args={
            "connect_timeout": cfg.db_connect_timeout_seconds,
            "application_name": "territory-run",
            "options": (
                f"-c statement_timeout={cfg.db_statement_timeout_ms} "
                f"-c lock_timeout={cfg.db_lock_timeout_ms} "
                f"-c idle_in_transaction_session_timeout={cfg.db_idle_transaction_timeout_ms}"
            ),
        },
    )
    if cfg.environment == "production":
        from app.db.privileges import enforce_runtime_privileges

        event.listen(result, "connect", enforce_runtime_privileges)
    return result


def get_session():
    with Session(engine()) as session, session.begin():
        yield session
