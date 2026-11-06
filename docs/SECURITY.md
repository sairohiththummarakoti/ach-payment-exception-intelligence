# Security boundaries

This is a synthetic educational simulation. The API never connects to banking rails and has no payment-send, reversal or cancellation operation. Moov is used solely to parse and validate text files. Upload attestation is required, but cannot detect genuine PII. Do not upload real financial records.

Request body and file limits are enforced separately. ASCII and MIME validation precede parsing. Generated names, account references and routing values are synthetic. Account names are discarded; account hashes/masks support duplicate comparison. HTTP logs include method and status only. Moov error bodies are redacted before persistence. Reviewer comments are length-limited and long digit sequences are redacted. A full enterprise DLP system is outside scope.

The model receives only prevalidated claims. It has one bounded call, no executable tools, no input document access and no arbitrary prose channel. Output schemas reject extra fields, unknown claim indexes and incomplete permutations. Procedure citations come from an allowlisted versioned corpus. Unknown codes, missing evidence and dependency failures remain visible.

Compose binds API, parser and database ports to 127.0.0.1. Set a unique `ACH_API_TOKEN` when needed. TLS, identity federation, fine-grained authorization, encrypted storage, retention controls and tamper-proof external audit storage are deployment responsibilities. Application audit events are append-only through this API; a database administrator can still modify records. Do not claim regulatory compliance or production banking readiness.

Report security issues through a private GitHub security advisory, without including live customer data or secrets.
