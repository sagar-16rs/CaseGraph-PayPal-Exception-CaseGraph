# Implementation changelog (per file)

Baseline: `research/.baseline/pre-20261108/` (gitignored local copy).
All paths are relative to the repository root.

## Cycle 3 — product transformation (dossier UI + readiness)

Driven by a rendered review of the cycle-2 interface: it was functional but read as
a generic admin dashboard (raw fact enums, JSON arrays as text, no visual hierarchy).
Direction and evidence in [`12-design-direction.md`](12-design-direction.md).

| File | Change |
| --- | --- |
| `backend/services/readiness.py` | New. Maps the eight PayPal dispute reasons to the evidence each actually needs, marks each requirement `present` / `missing` / `unknown` against attached evidence and the graph's `MISSING_EVIDENCE` nodes, and reports coverage plus the next concrete step. Exposed with an explicit `basis` string so nobody mistakes it for an outcome prediction. |
| `backend/services/explanations.py` | Includes `readiness`; `next_step` no longer embeds an ALL_CAPS action enum in prose. |
| `backend/ai/providers/rules.py` | Emits only facts an investigator reasons *about* (`GRAPH_FACT_REFS`), in a deliberate order, with human titles (`FACT_TITLES`). Removes JSON-valued and timestamp-valued nodes from the graph. |
| `scripts/demo_seed.py` | Fixed a real bug: the script counted existing analyses and then ignored the count, so every re-seed replayed the first analysis instead of re-analysing. |
| `frontend/src/styles.css` | Replaced the card-dashboard stylesheet with the dossier design system (warm paper, ink, hairline rules, one signal colour, three-role typography, tabular numerals). |
| `frontend/src/lib/format.ts` | New. Fact/reason/action/status label maps, money and date formatting, deadline urgency, and the case-detail → labelled-rows projection. Internal identifiers no longer reach the screen. |
| `frontend/src/App.tsx` | Rebuilt as a three-pane shell (docket · canvas · inspector) with a persistent verdict bar, deep-linkable views (`?view=`), and auto-loaded posture. |
| `frontend/src/components/CaseDocket.tsx` | New. Case list ordered by deadline, with urgency styling. |
| `frontend/src/components/CaseHeader.tsx` | New. Case identity, revision/deadline meta, and the always-visible verdict bar. |
| `frontend/src/components/Inspector.tsx` | New. Node provenance inspector, or case posture (readiness + policy findings) when nothing is selected. |
| `frontend/src/components/ReadinessPanel.tsx` | New. Coverage meter and per-requirement status. |
| `frontend/src/components/Timeline.tsx` | New. Event spine over evidence, graph revisions and approvals. |
| `frontend/src/components/GraphCanvas.tsx`, `lib/graph.ts` | Restyled; layout reduced to a predictable top-aligned stack of narrower columns after a layered "average of parents" variant was tried and rejected (see the comment in `lib/graph.ts`). |
| `frontend/src/components/ExplanationPanel.tsx`, `ActionComposer.tsx` | Rebuilt on the dossier type and colour system; the composer shows the human action name rather than the enum. |
| `frontend/src/components/SafetyFindings.tsx` | Retired: its responsibility moved into `Inspector` so case posture has one home. |
| `research/aris-casegraph-audit/figures/` | Architecture diagram from the ARIS `figure-spec` renderer (spec + SVG + PNG) and five interface captures. |
| `tests/test_explanations.py` | Four tests for readiness: reason mapping, coverage semantics, missing vs unknown, and the explanation embedding it. |

## Cycle 2 additions

| File | Change |
| --- | --- |
| `backend/services/explanations.py` | New. Deterministic explanation artifact: bounded provenance paths from each supporting node to source-backed roots, ungrounded-inference detection, contradiction set with an "affects recommendation" flag, evidence gaps, policy findings with plain-language explanations, confidence against the policy threshold, and a required next step. No model call; identical rows produce an identical document. |
| `backend/api/ai.py` | Added `GET /{case_id}/ai/analyses/{analysis_uid}/explain`. |
| `backend/security/policy.py` | Added the route rule (VIEWER, own rate-limit bucket) ahead of the generic case-read rule. |
| `backend/services/cases.py` | Extracted `_detail_payload`, added `CaseService.list_details()` with four batched reads, and reused the same serializer from `detail()` so the two paths cannot drift. |
| `backend/api/cases.py` | `list_cases` now uses the batched projection instead of a per-case `detail()` loop. |
| `backend/config.py`, `backend/paypal/http.py` | `PAYPAL_MULTIPART_TIMEOUT_SECONDS` replaces the hard-coded 60 s upload timeout. |
| `frontend/src/components/ExplanationPanel.tsx` | New. Renders the export: verdict, next step, confidence-vs-policy, grounding paths as clickable source chips, contradictions, gaps, findings, stated uncertainties, JSON export. |
| `frontend/src/components/ErrorBoundary.tsx`, `frontend/src/main.tsx` | New boundary; a malformed payload shows a contained failure screen instead of a blank app. |
| `frontend/src/App.tsx`, `api/client.ts`, `api/types.ts` | Explanation state, loader, panel in the AI tab, `Explanation` types and the `explain` client call. |
| `tests/test_explanations.py` | New. 8 tests: grounding terminates in cited sources, the contradiction that downgraded the action is surfaced, confidence vs threshold, determinism, 404, finding-code coverage, board/single-case parity, constant query count. |
| `tests/test_http_journey.py` | Added the `/explain` route test and the case-board listing test. |
| `tests/test_frontend_contract.py` | Added the audit-export and error-boundary invariants. |

## Backend — correctness

| File | Change |
| --- | --- |
| `backend/api/actions.py` | Annotated every handler parameter and pinned response models. This is the fix for the 422-on-approval defect; also added a comment explaining why annotations are load-bearing. |
| `backend/api/safety.py` | Annotated `case_id` / `analysis_uid` for the same reason. |
| `backend/db/models.py` | `ActionReconciliation` now stores `resulting_execution_status`, `observed_snapshot_hash`, `details_json`, `details_hash`, `record_hash` instead of `before_status`, `after_status`, `paypal_snapshot_hash`, `detail_json`, `detail_hash`. |
| `backend/work/domain.py` | `ReconciliationMethod` → `AUTO_PAYPAL_STATE`, `MANUAL_PAYPAL_DASHBOARD`; `ReconciliationOutcome` → `CONFIRMED_EXECUTED`, `CONFIRMED_NOT_EXECUTED`, `INCONCLUSIVE`, each with a comment explaining the safety semantics. |
| `backend/work/schemas.py` | `ManualReconciliationRequest` now takes `decision` (the field the service reads) with a literal type; `ReconciliationResponse` matches what the service actually returns. |
| `backend/work/reconciliation.py` | `_response()` reads the new columns and no longer takes an unused status argument; manual reconciliation rejects a missing `confirmed_from_paypal_dashboard` with 422 and rejects unknown decisions; error strings and detail payloads match the new vocabulary. |
| `backend/security/jwt_auth.py` | Added `_signing_key` / `_refresh_for_unknown_kid`: one forced JWKS refresh per 5 s window when a token's `kid` is unknown, under a lock, with failures mapped to a generic authentication error. |
| `backend/db/migrations.py` | `expected_head_revision()` → `20261108_0010`, exported as a named constant. |
| `backend/services/cases.py` | `detail()` exposes a boolean `simulated` derived from the stored PayPal payload, so the UI can label the demo transport. No new state. |
| `migrations/versions/20261108_0010_reconciliation_alignment.py` | New conditional migration: aligns the reconciliation table on databases created from the old metadata, no-op on fresh ones (because `0007` creates from current metadata), reverses cleanly. |
| `scripts/integration_gate.py` | Removed the drifted hard-coded `"20261025_0008"` literal; the gate now compares only against `expected_head_revision()`. |
| `scripts/freeze_validation_protocol.py` | Protocol-lock artifact keys use POSIX separators. |
| `scripts/reconcile_action.py` | Unchanged — it already passed `decision=`; it now matches the schema it targets. |

## Backend — demonstration capability (new)

| File | Purpose |
| --- | --- |
| `backend/paypal/simulation_data.py` | Three deterministic dispute fixtures plus reference evidence, shaped like `GET /v1/customer/disputes/{id}`. |
| `backend/paypal/simulator.py` | Stateful simulated Disputes API: renders HATEOAS links per status, mutates status on writes, bumps `simulation_revision`, stamps `simulated: true`, injects transport/5xx faults on writes only, persists to a JSON file so API and worker processes agree. |
| `backend/paypal/http.py` | Transport delegation. Reads the simulator for `get_dispute`, `list_disputes`, `verify_webhook`, and all eight write operations. Also honours `paypal_timeout_seconds` for JSON calls (previously hard-coded 30 s). |
| `backend/ai/providers/rules.py` | Deterministic reference reasoner: fact nodes copied byte-exact from PayPal facts, claim nodes with verbatim excerpts and speaker validation, one grounded inference, contradiction detection, missing-evidence detection for not-received / not-as-described reasons, and a conservative recommendation table that never proposes a high-risk action when the evidence conflicts. |
| `backend/ai/service.py` | `default_reasoning_provider()` implements `CASEGRAPH_AI_PROVIDER=openai|rules|auto`; `auto` prefers OpenAI with a key and falls back to rules **outside production only**. |
| `backend/config.py` | New settings: `paypal_transport`, `simulation_state_path`, `simulated_fault`, `ai_provider`; `simulated_paypal` property; `validate_paypal_sandbox` short-circuits for the simulator. |
| `backend/main.py` | Production startup refuses the simulated transport. |
| `backend/security/config.py` | Production configuration validation reports the simulated transport as an error. |
| `scripts/demo_seed.py` | Seeds the three demo cases through the real service paths, prints the provider used and the analysis outcome. Refuses to run unless the transport is simulated. |
| `scripts/regenerate_manifest.py` | Regenerates or `--check`s `MANIFEST.sha256` over the distributable tree with POSIX paths and an explicit exclusion list. |

## Frontend — rebuilt

| File | Change |
| --- | --- |
| `frontend/src/App.tsx` | Rewritten as a shell: case rail, case header with revision and safety badge, five tabs, readiness checklist, analysis history, approval and reconciliation trails. Kept the contract strings the tests assert on (`'overview'`, `'graph'`, `'evidence'`, `'ai'`, `'actions'`, `Run analysis`, `Execute approved action`, `Read-only reconcile`). |
| `frontend/src/components/GraphCanvas.tsx` | New. Renders the graph with deterministic column layout, SVG provenance curves, dashed red contradiction edges, hover/selection focus dimming, per-node confidence and source reference, and a legend that names each epistemic type. |
| `frontend/src/components/SafetyFindings.tsx` | New. Turns finding codes into plain-language explanations with severity chips and clickable node references, plus a collapsed raw report for audit. |
| `frontend/src/components/ActionComposer.tsx` | New. Typed form per action type replacing the raw-JSON textarea, with a live preview of the exact payload, amount/currency bounds from PayPal state, file-hash binding for evidence, and server-side validation retained as the authority. |
| `frontend/src/lib/graph.ts` | New. Column layout maths, edge curves, node accent mapping. |
| `frontend/src/styles.css` | Replaced the minified single-line stylesheet with a token-based design system (surfaces, epistemic accent colours, graph canvas, findings, composer, tables) and responsive breakpoints. |
| `frontend/src/api/client.ts` | Added `reconciliations(caseId, actionUid)`. Existing signatures preserved (`executeAction` still sends only `approval_hash`). |
| `frontend/src/api/types.ts` | Added `Reconciliation`, `SafetyFinding`, and `CaseDetail.simulated`. |

## Tests

| File | Change |
| --- | --- |
| `tests/conftest.py` | New. Binds the suite to an isolated per-process SQLite file when `DATABASE_URL` is unset (deleting any stale file first), and defaults the environment to test/disabled-auth. |
| `tests/test_reconciliation.py` | New. Executes auto reconciliation (inconclusive vs confirmed), the manual confirmation gate, the release path, history integrity, and the execution-boundary block. |
| `tests/test_demo_simulation.py` | New. Seeds the three demo disputes and asserts distinct safety outcomes, a real simulated write, the ambiguous-write block, and the release path. |
| `tests/test_http_journey.py` | New. Drives the ASGI app: sync → intake → analyze → safety → approve (JSON body) → execute → history → reconciliation list; plus wrong-hash and payload-mismatch rejections. This is the regression test for the FastAPI binding defect. |
| `tests/test_frontend_contract.py` | Retargeted to assert product invariants across `frontend/src` rather than string-matching a single file, and added an assertion that a real graph renderer exists. |

## Docs and metadata

| File | Change |
| --- | --- |
| `README.md` | New "Try it in two minutes (no credentials)" section with the three demo disputes, the fault-injection walkthrough, and the reconciliation CLI; updated layout; noted that `pytest` is now safe to run; clarified the licence gate. |
| `.env.example` | Documents `CASEGRAPH_PAYPAL_TRANSPORT`, `CASEGRAPH_SIMULATION_STATE`, `CASEGRAPH_SIMULATED_FAULT`, `CASEGRAPH_AI_PROVIDER`. |
| `VERSION` | `1.0.0-rc1` → `1.0.0-rc2`. |
| `CHANGELOG.md` | Full rc2 entry describing every defect and capability above. |
| `.gitignore` | Ignores `frontend/*.tsbuildinfo`, `research/.tmp/`, `research/.baseline/`, and ACL recovery output. |
| `MANIFEST.sha256` | Regenerated (228 files) with `scripts/regenerate_manifest.py`. |
| `data/submission/submission.json` | `functional_demo_mode: hosted → source` (accurate now that the product runs without credentials); ai_tools and paypal_tools updated to describe the simulator and reference reasoner. Repo/video/licence/contact remain `CHANGE_ME` — owner decisions. |

## Not changed, deliberately

`backend/services/actions.py`, `backend/safety/*`, `backend/casegraph/validate.py`,
`backend/uploads/*`, `backend/security/{middleware,policy,rate_limit}.py`, and the
financial idempotency model. They are the parts that must not be weakened, and the
audit found no defect in them worth the risk of touching them in a short cycle.
