# Demonstration

Run `uv sync --frozen`, then `uv run ach-demo generate`. The checked-in `data/fixtures/manifest.json` labels 37 deterministic files. Regeneration is byte-reproducible. `uv run ach-demo demo` migrates the local SQLite database, ingests the incorrect-credit-control fixture, retrieves a cited explanation and appends a human comment. Re-running it is safe: the file UUID remains the same and another upload/comment is auditable.

To exercise the external stack, run `docker compose up --build -d --wait`, then `docker compose exec api ach-demo smoke --url http://localhost:8001`. The smoke runner verifies readiness, a valid upload, an invalid upload, a cited explanation, a reviewer comment and audit persistence over actual HTTP. The UI is FastAPI's interactive `/docs` interface.

In the interactive API, select POST files, enter `true` for `x-synthetic-data`, and upload `bad_batch_credit.ach`. Copy the returned exception ID with code `BATCH_CREDIT_TOTAL` into the explain endpoint. The report states that computed value 12345 differs from recorded value 1; its citation points to `ach-analyst-procedures`, version `2026-11-05.1`, section `controls`. Use the review endpoint with `expected_version: 0` and `action: escalate`. Retrieve the audit endpoint to see the decision and explanation metadata.

Optional local inference: install Ollama separately, pull the chosen local model, set `ACH_LLM_PROVIDER=ollama` and `ACH_OLLAMA_MODEL` before starting the API. The service calls `/api/generate` at the configured `ACH_OLLAMA_URL`. It sends only fixed evidence claims, never account data. The LLM returns claim indexes, not arbitrary factual text. No successful live model call is claimed by the offline evaluation.

Stop containers with `docker compose down`. Evidence remains in the named volume. Do not reuse the synthetic Compose credentials or expose these demo services publicly without deployment hardening.
