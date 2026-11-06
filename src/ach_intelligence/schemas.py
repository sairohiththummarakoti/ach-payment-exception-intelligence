from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Finding(StrictModel):
    code: str
    severity: Literal["error", "warning"] = "error"
    message: str
    line: int | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    source: Literal["local", "moov"] = "local"


class Entry(StrictModel):
    line: int
    batch_number: str
    trace: str
    account_hash: str
    account_mask: str
    routing_mask: str
    amount_cents: int
    direction: Literal["credit", "debit"]
    effective_date: str
    duplicate_key: str


class Batch(StrictModel):
    number: str
    sec: str
    effective_date: str
    entry_count: int
    credit_cents: int
    debit_cents: int
    entry_hash: int


class ParsedFile(StrictModel):
    fingerprint: str
    batches: list[Batch] = Field(default_factory=list)
    entries: list[Entry] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    record_count: int
    credit_cents: int = 0
    debit_cents: int = 0


class Citation(StrictModel):
    document: str
    version: str
    section: str
    text: str


class Claim(StrictModel):
    text: str
    evidence_ids: list[str]


class Explanation(StrictModel):
    exception_id: str
    claims: list[Claim]
    citations: list[Citation]
    uncertainty: list[str]
    next_steps: list[str]
    requires_human_review: bool = True
    model_metadata: dict[str, Any]
    tool_invocations: list[dict[str, Any]]


class ReviewRequest(StrictModel):
    action: Literal["approve", "reject", "escalate", "comment"]
    reviewer: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9 _.-]+$")
    comment: str = Field(default="", max_length=2000)
    expected_version: int = Field(ge=0)


class ReturnRequest(StrictModel):
    code: str = Field(pattern=r"^R\d{2}$")
