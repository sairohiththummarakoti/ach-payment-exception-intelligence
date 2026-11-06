from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .adapters import MoovAdapter, redact
from .config import Settings
from .db import AuditRow, BatchRow, EntryRow, ExceptionRow, FileRow, transaction, uid
from .intelligence import explain
from .parser import parse
from .schemas import Finding, ReviewRequest


class NotFound(LookupError):
    pass


class ReviewConflict(ValueError):
    pass


def get_file(session: Session, file_id: str) -> FileRow:
    row = session.get(FileRow, file_id)
    if row is None:
        raise NotFound("File not found")
    return row


def summary(session: Session, row: FileRow) -> dict[str, Any]:
    exceptions = list(session.scalars(select(ExceptionRow).where(ExceptionRow.file_id == row.id)))
    return {
        "id": row.id,
        "fingerprint": row.fingerprint,
        "validation_status": row.status,
        "created_at": row.created_at,
        **row.data,
        "exceptions": [
            {"id": e.id, "state": e.state, "version": e.version, **e.finding} for e in exceptions
        ],
    }


def ingest(engine: Engine, settings: Settings, data: bytes) -> dict[str, Any]:
    parsed = parse(data, frozenset(settings.duplicate_keys.split(",")))
    if settings.moov_url:
        moov_findings, adapter = MoovAdapter(settings.moov_url).validate(data)
        parsed.findings.extend(moov_findings)
    else:
        adapter = {
            "adapter": "local-limited-profile",
            "version": "1",
            "status": "offline",
            "limitation": "Moov validation was not performed.",
        }
    with transaction(engine, write=True) as session:
        existing = session.scalar(select(FileRow).where(FileRow.fingerprint == parsed.fingerprint))
        if existing:
            duplicate = session.scalar(
                select(ExceptionRow).where(
                    ExceptionRow.file_id == existing.id, ExceptionRow.code == "DUPLICATE_FILE"
                )
            )
            if duplicate is None:
                finding = Finding(
                    code="DUPLICATE_FILE",
                    severity="warning",
                    message="This exact file fingerprint has already been uploaded.",
                    evidence={"original_file_id": existing.id, "fingerprint": parsed.fingerprint},
                )
                session.add(
                    ExceptionRow(
                        file_id=existing.id, code=finding.code, finding=finding.model_dump()
                    )
                )
                if existing.status == "valid":
                    existing.status = "needs_review"
            session.add(
                AuditRow(
                    file_id=existing.id,
                    exception_id=None,
                    action="duplicate_upload",
                    actor="system",
                    data={"fingerprint": parsed.fingerprint},
                )
            )
            session.flush()
            return {**summary(session, existing), "duplicate_upload": True}
        row = FileRow(id=uid(), fingerprint=parsed.fingerprint, status="valid", data={})
        session.add(row)
        session.flush()
        for entry in parsed.entries:
            predicates = []
            if "account_amount_date" in settings.duplicate_keys.split(","):
                predicates.append(EntryRow.duplicate_key == entry.duplicate_key)
            if "trace" in settings.duplicate_keys.split(","):
                predicates.append(EntryRow.trace == entry.trace)
            if predicates:
                others = list(
                    session.scalars(
                        select(EntryRow)
                        .where(or_(*predicates), EntryRow.file_id != row.id)
                        .limit(10)
                    )
                )
                if others:
                    parsed.findings.append(
                        Finding(
                            code="CROSS_FILE_DUPLICATE",
                            severity="warning",
                            message="Configured duplicate keys match previously ingested entry evidence.",
                            line=entry.line,
                            evidence={
                                "matching_entry_ids": [e.id for e in others],
                                "matching_file_ids": sorted({e.file_id for e in others}),
                                "keys": settings.duplicate_keys.split(","),
                            },
                        )
                    )
            session.add(
                EntryRow(
                    file_id=row.id,
                    duplicate_key=entry.duplicate_key,
                    trace=entry.trace,
                    data=entry.model_dump(),
                )
            )
        for batch in parsed.batches:
            session.add(BatchRow(file_id=row.id, data=batch.model_dump()))
        for finding in parsed.findings:
            session.add(
                ExceptionRow(file_id=row.id, code=finding.code, finding=finding.model_dump())
            )
        row.status = (
            "invalid"
            if any(f.severity == "error" for f in parsed.findings)
            else ("needs_review" if parsed.findings else "valid")
        )
        row.data = {
            "record_count": parsed.record_count,
            "batch_count": len(parsed.batches),
            "entry_count": len(parsed.entries),
            "credit_cents": parsed.credit_cents,
            "debit_cents": parsed.debit_cents,
            "currency": "USD",
            "synthetic": True,
            "adapter": adapter,
            "duplicate_keys": settings.duplicate_keys.split(","),
        }
        session.add(
            AuditRow(
                file_id=row.id,
                exception_id=None,
                action="ingest",
                actor="system",
                data={"finding_count": len(parsed.findings), "adapter": adapter},
            )
        )
        session.flush()
        return {**summary(session, row), "duplicate_upload": False}


def explain_exception(engine: Engine, settings: Settings, exception_id: str) -> dict[str, Any]:
    with transaction(engine) as session:
        row = session.get(ExceptionRow, exception_id)
        if row is None:
            raise NotFound("Exception not found")
        finding = Finding.model_validate(row.finding)
        file_id = row.file_id
    report = explain(exception_id, finding, settings)
    with transaction(engine, write=True) as session:
        audit = AuditRow(
            file_id=file_id,
            exception_id=exception_id,
            action="explain",
            actor="system",
            data=report.model_dump(),
        )
        session.add(audit)
        session.flush()
        return {**report.model_dump(), "audit_id": audit.id}


def review(engine: Engine, exception_id: str, request: ReviewRequest) -> dict[str, Any]:
    with transaction(engine, write=True) as session:
        row = session.get(ExceptionRow, exception_id)
        if row is None:
            raise NotFound("Exception not found")
        if row.version != request.expected_version:
            raise ReviewConflict("The exception changed; refresh before recording a decision.")
        if row.state in {"approved", "rejected"} and request.action != "comment":
            raise ReviewConflict("A closed disposition accepts comments only.")
        before = row.state
        row.state = {"approve": "approved", "reject": "rejected", "escalate": "escalated"}.get(
            request.action, row.state
        )
        row.version += 1
        audit = AuditRow(
            file_id=row.file_id,
            exception_id=row.id,
            action=request.action,
            actor=request.reviewer,
            data={
                "from": before,
                "to": row.state,
                "comment": redact(request.comment),
                "version": row.version,
            },
        )
        session.add(audit)
        session.flush()
        return {
            "exception_id": row.id,
            "state": row.state,
            "version": row.version,
            "audit_id": audit.id,
            "payment_action": None,
        }
