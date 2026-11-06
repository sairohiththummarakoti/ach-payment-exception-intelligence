from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, ForeignKey, String, create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def uid() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class FileRow(Base):
    __tablename__ = "ach_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class BatchRow(Base):
    __tablename__ = "ach_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    file_id: Mapped[str] = mapped_column(ForeignKey("ach_files.id"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class EntryRow(Base):
    __tablename__ = "ach_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    file_id: Mapped[str] = mapped_column(ForeignKey("ach_files.id"), index=True)
    duplicate_key: Mapped[str] = mapped_column(String(64), index=True)
    trace: Mapped[str] = mapped_column(String(15), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class ExceptionRow(Base):
    __tablename__ = "ach_exceptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    file_id: Mapped[str] = mapped_column(ForeignKey("ach_files.id"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    state: Mapped[str] = mapped_column(String(20), default="open")
    version: Mapped[int] = mapped_column(default=0)
    finding: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditRow(Base):
    __tablename__ = "ach_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    file_id: Mapped[str] = mapped_column(ForeignKey("ach_files.id"), index=True)
    exception_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


def make_engine(url: str) -> Engine:
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args=(
            {"check_same_thread": False, "timeout": 15}
            if url.startswith("sqlite")
            else {"connect_timeout": 5}
        ),
    )
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection: Any, _: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=15000")

    return engine


def migrate(engine: Engine) -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@contextmanager
def transaction(engine: Engine, *, write: bool = False) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        if write:
            if engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            else:
                # Serialize the small educational ingestion/review workload across processes.
                session.execute(text("SELECT pg_advisory_xact_lock(73415821)"))
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
