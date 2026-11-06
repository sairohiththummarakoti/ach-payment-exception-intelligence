# Evaluation

Run `uv run ach-demo evaluate --output artifacts/evaluation.json`. The checked-in `evaluation-results.json` is an actual execution result for `synthetic-ach-v1`, generated from the same deterministic fixture generator as the checked-in ACH files. It is not a benchmark on real banking files.

| Metric | Observed | Denominator |
|---|---:|---|
| Validation classification and expected finding | 37 / 37 | Labeled file scenarios, including valid profiles, malformed fields, duplicates and injected receiver text |
| Return definition or explicit unknown | 6 / 6 | R01, R02, R03, R04, R29, R99 |
| Valid procedure citations | 58 / 58 | Reports produced for each finding across scenarios |
| Required procedure section retrieved | 58 / 58 | Same finding reports |
| Supported factual claims | 143 / 143 | Fixed claims verified against the finding ID, record index and calculated/observed fields |
| Unsupported factual claim rate | 0 / 143 | Same factual claims |

The evaluation checks actual emitted claims against evidence rather than merely counting citation presence. Procedure citation checks compare document text, section and version. Retrieval checks require the relevant labeled section, not just any citation. The next-step list is a fixed analyst checklist and does not contain dynamic financial recommendations. These results do not establish unconstrained LLM performance; optional model output is restricted to a permutation of these facts and is tested against fabricated indexes/fields.

Unit and API tests additionally verify request limits, invalid media/encoding, prompt-injection handling, unknown IDs, invalid tool fields, two-process-style persistence, concurrent upload idempotency, stale review rejection, closed-state transitions, account redaction, and failure of configured Moov dependencies. A mutation regression checks every character position across representative record types for parser crashes.

The live integration test is skipped unless `TEST_MOOV_URL` is configured. CI provides Moov and PostgreSQL, then explicitly runs it. The HTTP smoke runner checks the full container stack. Optional Ollama live inference is not part of CI and is not included in the measured results. No tests use paid keys.
