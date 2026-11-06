# Development instructions

Use Python 3.12 and `uv sync --frozen`. Source is in `src/ach_intelligence`; domain validation, persistence, adapters and API are separated. Money is integer cents. Run Ruff check/format, mypy, pytest and `ach-demo evaluate` after meaningful changes. Never edit fixture expectations just to match changed behavior.

All data must be synthetic. No payment execution endpoints or tools. Keep dependency timeouts and request limits bounded. Never log request bodies, accounts, tokens or LLM prompts. Add a versioned migration for schema changes; do not rewrite revision 0001 for subsequent releases. New AI claims require validated evidence and citation provenance. Human review must never convert invalid input into valid input. Preserve optimistic concurrency, idempotency and audit records. Do not silently fall back from an enabled failing external parser.
