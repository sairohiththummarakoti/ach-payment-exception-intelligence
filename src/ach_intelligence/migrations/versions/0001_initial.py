"""Initial immutable schema revision."""

from alembic import op
from sqlalchemy import JSON, Column, ForeignKey, Integer, String

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ach_files",
        Column("id", String(36), primary_key=True),
        Column("fingerprint", String(64), nullable=False, unique=True),
        Column("status", String(30), nullable=False),
        Column("data", JSON, nullable=False),
        Column("created_at", String(40), nullable=False),
    )
    op.create_table(
        "ach_batches",
        Column("id", String(36), primary_key=True),
        Column("file_id", String(36), ForeignKey("ach_files.id"), nullable=False),
        Column("data", JSON, nullable=False),
    )
    op.create_index("ix_ach_batches_file_id", "ach_batches", ["file_id"])
    op.create_table(
        "ach_entries",
        Column("id", String(36), primary_key=True),
        Column("file_id", String(36), ForeignKey("ach_files.id"), nullable=False),
        Column("duplicate_key", String(64), nullable=False),
        Column("trace", String(15), nullable=False),
        Column("data", JSON, nullable=False),
    )
    for column in ("file_id", "duplicate_key", "trace"):
        op.create_index(f"ix_ach_entries_{column}", "ach_entries", [column])
    op.create_table(
        "ach_exceptions",
        Column("id", String(36), primary_key=True),
        Column("file_id", String(36), ForeignKey("ach_files.id"), nullable=False),
        Column("code", String(60), nullable=False),
        Column("state", String(20), nullable=False),
        Column("version", Integer, nullable=False),
        Column("finding", JSON, nullable=False),
    )
    op.create_index("ix_ach_exceptions_file_id", "ach_exceptions", ["file_id"])
    op.create_table(
        "ach_audit",
        Column("id", String(36), primary_key=True),
        Column("file_id", String(36), ForeignKey("ach_files.id"), nullable=False),
        Column("exception_id", String(36)),
        Column("action", String(40), nullable=False),
        Column("actor", String(80), nullable=False),
        Column("data", JSON, nullable=False),
        Column("created_at", String(40), nullable=False),
    )
    for column in ("file_id", "exception_id"):
        op.create_index(f"ix_ach_audit_{column}", "ach_audit", [column])


def downgrade() -> None:
    for name in ("ach_audit", "ach_exceptions", "ach_entries", "ach_batches", "ach_files"):
        op.drop_table(name)
