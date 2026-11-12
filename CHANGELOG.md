# Changelog

## 1.0.0-rc2 — submission-candidate hardening

### Cycle 4 — release completion and cross-platform stabilization

- **OpenAI-compatible Chat Completions / DeepSeek adapter.** `OpenAIReasoningProvider`
  (`backend/ai/providers/openai.py`) now supports both OpenAI `/v1/responses`
  (Structured Outputs) and `/v1/chat/completions` (`response_format={"type":
  "json_object"}` + strict `AIOutput` + `validate_ai_output` validation) controlled
  via `CASEGRAPH_AI_API_MODE=auto|responses|chat_completions` and
  `CASEGRAPH_AI_PROVIDER=auto|openai|deepseek|rules`. In `auto` mode, DeepSeek base
  URLs (`api.deepseek.com`) and custom gateways that return 404/400 on `/responses`
  automatically route to `/v1/chat/completions`.
- **MIT License and submission metadata.** Added `LICENSE` (MIT), updated `README.md`,
  and recorded `"open_source_license": "MIT"` in `data/submission/submission.json`.
- **Environment template sanitization and secret-scanner hardening.** Removed
  accidentally populated sandbox credentials and `OPENAI_BASE_URL` from
  `.env.example`, enabled `PAYPAL_WEBHOOK_VERIFY=true` by default in `.env.example`,
  and added PayPal secret pattern detection and scratch-directory exclusions to
  `submission/submission.py`, `scripts/release_scan.py`, and
  `scripts/verify_public_release.py`.
- **Cross-platform manifest determinism and migration idempotency.** Fixed
  `scripts/regenerate_manifest.py` to sort entries by POSIX path string rather than
  OS-dependent `Path` comparison; made migration `20261025_0008` idempotent when
  `evidence_files` already exists; and added automatic `atexit` cleanup of
  per-process `pytest-<pid>.db` files in `tests/conftest.py`.

### Cycle 2 & 3 additions

Deferred items from the first audit cycle, delivered after a novelty review
changed the positioning (see `research/aris-casegraph-audit/11-novelty-check.md`):

- **Dossier workspace and dispute readiness.** Replaced the card-dashboard UI with
  the three-pane dispute dossier (`CaseDocket`, `CaseHeader`, `GraphCanvas`,
  `Inspector`, `ReadinessPanel`, `Timeline`) and deterministic per-reason evidence
  readiness (`backend/services/readiness.py`).
- **Exportable audit explanation.** `GET /api/cases/{id}/ai/analyses/{uid}/explain`
  returns a deterministic document assembled from the persisted analysis, graph
  revision, and safety assessment: grounding paths to source-backed roots, the
  contradictions that affected the recommendation, evidence gaps, policy findings
  with plain-language explanations, confidence against the policy threshold, and
  the required next step. No model call, so the same rows always produce the same
  document. Rendered in the workspace by `ExplanationPanel`.
- **Constant-query case board.** `GET /api/cases` previously issued four queries
  per case; it now uses one batched projection (`CaseService.list_details`) and a
  test asserts the query count stays flat as cases are added.
- **Frontend error boundary.** A malformed payload now shows a contained failure
  screen instead of a blank application.
- **Configurable multipart timeout.** `PAYPAL_MULTIPART_TIMEOUT_SECONDS` replaces
  the hard-coded 60 s used for PayPal evidence uploads.

### Correctness fixes

Correctness fixes found by driving every user-facing path through the HTTP
application instead of the service layer:

- **Human approval and execution were unusable over HTTP.** The `approve` and
  `execute` handlers in `backend/api/actions.py` had unannotated parameters, so
  FastAPI parsed the request body as a required query parameter and every browser
  approval returned 422. Handlers are now fully annotated and covered by
  `tests/test_http_journey.py`.
- **Reconciliation was dead code.** `backend/work/reconciliation.py` referenced
  ORM columns, response fields, and enum members that did not exist
  (`resulting_execution_status`, `details_json`, `record_hash`,
  `ReconciliationMethod.AUTO_PAYPAL_STATE`, `ReconciliationOutcome.INCONCLUSIVE`).
  Any attempt to resolve an `UNKNOWN_OUTCOME` action raised `TypeError`, leaving
  the case permanently blocked from further PayPal writes. The model, schemas,
  enums, service, CLI, and a new Alembic revision (`20261108_0010`) now agree, and
  `tests/test_reconciliation.py` executes the real paths.
- **Manual reconciliation now fails closed.** `confirmed_from_paypal_dashboard`
  is enforced by the service, not only by the CLI argument parser.
- **OIDC key rotation no longer rejects valid tokens for 30 seconds.** A forced,
  rate-limited JWKS refresh handles an unknown `kid` immediately.
- `scripts/integration_gate.py` compared the migration head against a second
  hard-coded literal that had already drifted from `expected_head_revision()`.
- Validation-protocol locks now store POSIX artifact paths, so a lock frozen on
  Windows verifies on Linux.

Test-suite safety:

- `tests/conftest.py` binds the suite to an isolated per-process SQLite file and
  removes it on exit. Test runs previously called `drop_all` against
  `.data/casegraph.db`, the same file the running application used, so a `pytest`
  invocation could delete local cases.

Runnable demonstration without credentials:

- Added a deterministic **simulated PayPal sandbox**
  (`backend/paypal/simulator.py`) selectable with
  `CASEGRAPH_PAYPAL_TRANSPORT=simulated`. It honours the real HATEOAS-link
  contract, stamps every payload `"simulated": true`, and is refused by the
  application and by security validation when `CASEGRAPH_ENV=production`.
- Added a deterministic **reference reasoner**
  (`backend/ai/providers/rules.py`, `CASEGRAPH_AI_PROVIDER=rules|auto`) so the
  reasoning → validation → safety pipeline runs without a model key. The
  provenance of the chosen provider is recorded per analysis.
- Added `scripts/demo_seed.py` and the fault injection setting
  `CASEGRAPH_SIMULATED_FAULT=timeout|server_error` to demonstrate the
  `UNKNOWN_OUTCOME` → reconciliation path end to end.

Workspace:

- Replaced the single-file, raw-JSON workspace with a componentised React UI:
  deterministic graph canvas with provenance edges and contradiction highlighting,
  human-readable safety findings with node-level drill-down, and a typed action
  composer for each PayPal action instead of a JSON textarea.

## 1.0.0-rc1

Initial consolidated release candidate.

Highlights:

- authoritative PayPal dispute synchronization and verified webhooks
- immutable case facts, evidence revisions, and provenance-aware CaseGraph revisions
- structured AI reasoning with deterministic compilation and safety evaluation
- typed human approval and fail-closed PayPal action execution
- durable work queue, per-dispute synchronization, dead-letter handling, and reconciliation
- OIDC/JWT authentication, RBAC, tenant binding, rate limiting, and security headers
- private evidence-file storage with MIME/signature validation, SHA-256 binding, and malware-scan policy
- React investigation workspace
- benchmark, controlled product-validation, and public-release tooling
- Docker/Compose deployment examples and CI workflow
