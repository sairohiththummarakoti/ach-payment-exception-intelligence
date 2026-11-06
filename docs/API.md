# API contract

All paths are under `/api/v1/ach` except `/health`. Interactive OpenAPI is at `/docs`. If `ACH_API_TOKEN` is set, use `Authorization: Bearer <your-local-token>` on every endpoint except health.

| Method and path | Input | Output |
|---|---|---|
| POST `/files` | Multipart `file`, `X-Synthetic-Data: true` | 201 file UUID, fingerprint, normalized counts/totals, findings, parser metadata |
| GET `/files` | None | Latest 100 file summaries |
| GET `/files/{id}` | UUID | Summary and current exception dispositions |
| GET `/files/{id}/entries` | UUID | Normalized entries with evidence IDs and masked accounts |
| GET `/files/{id}/exceptions` | UUID | Findings with severity, evidence, review state and version |
| GET `/files/{id}/audit` | UUID | Ordered ingestion, explanation and review audit records |
| POST `/exceptions/{id}/explain` | No body | Claims, evidence IDs, versioned procedure citations, uncertainty, next steps, model and tool metadata |
| POST `/exceptions/{id}/review` | action, reviewer, comment, expected_version | New disposition/version and audit UUID |
| POST `/returns/interpret` | `{"code":"R01"}` | Reference definition or explicit unknown; no transaction conclusion |
| GET `/health` | None | Database and configured Moov readiness, active mode |

Uploads accept `text/plain` or `application/octet-stream`, ASCII, and at most 1 MiB by default. The complete multipart request is bounded to the file limit plus 16 KiB. Unsupported media returns 415; oversized data returns 413; invalid encoding/schema returns 422; absent synthetic attestation returns 400. Domain-invalid ACH files are persisted and return 201 with `validation_status: invalid`, not a false success. Parser dependency failure returns 503 and does not accept the file.

File states are `valid`, `needs_review`, `invalid`. Exception dispositions are separate: `open`, `escalated`, `approved`, `rejected`. Approve/reject/escalate are allowed from open/escalated; comments are allowed in any state. A stale version or attempted change to a closed decision returns 409. Re-uploading identical bytes returns the same file UUID and records a duplicate-upload audit event; it never duplicates entries. IDs that do not exist return 404.

Example control evidence: `{"code":"BATCH_CREDIT_TOTAL","severity":"error","line":5,"evidence":{"expected":12345,"observed":1}}`. Explanation claims refer to the persisted exception UUID. Monetary totals are cents; currency is USD. Source file record numbers are one-based.
