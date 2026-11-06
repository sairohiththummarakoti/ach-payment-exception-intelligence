# Requirements traceability

This project implements the ACH application from the supplied Banking AI Open Source Projects requirements brief. Scope is ordinary synthetic PPD/CCD entries without addenda; unsupported SEC and transaction profiles are reported explicitly.

| Requirement | Implementation | Verification |
|---|---|---|
| ACH-01 | API multipart ASCII/MIME/body limits and synthetic attestation | API boundary tests |
| ACH-02 | Pinned official Moov HTTP container and normalized errors | Real-adapter test and container smoke |
| ACH-03, ACH-04 | Sequence/header/routing/date/trace/service/count/hash/total checks | 37 labeled fixtures and mutation regression |
| ACH-05 | Fingerprint, in-file and configured cross-file duplicate comparison | Duplicate and concurrent-ingestion tests |
| ACH-06 | SQLAlchemy tables for files, batches, entries, findings and audit, Alembic migration | Persistence across new app instances and PostgreSQL integration |
| ACH-07 | Locally authored versioned return-code notes with unknown handling | Six return lookups |
| ACH-08 | LangChain retriever and cited schema-validated evidence reports | Retrieval, citation and claim evaluation |
| ACH-09 | Four review actions, optimistic locking, immutable validation state | Transition, stale-version and audit tests |
| ACH-10 | No-key deterministic path, optional bounded Ollama claim ordering | Offline tests and adversarial model-adapter tests |
| ACH-11 | Measured validation, retrieval, citation and unsupported-claim metrics | Evaluation command/report |
| ENG-01–06 | Python3.12, Pydantic, modules, exact deps/uv.lock, Compose, health, migrations, docs/CI/license | Local checks, Docker and published CI |
| AI-01–06 | Evidence-only facts, allowlisted sections, bounded LLM, uncertainty, metadata/audit | Injection/schema/unsupported-claim tests |
| SEC-01–05 | Synthetic fixtures, redaction, limits, human dispositions, original notes, publication secret scan | Security tests and release review |

External Moov validation is a separate mode and is not silently claimed in offline runs. Optional live model inference and production infrastructure hardening are not part of the deterministic acceptance measurement.
