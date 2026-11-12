# Codebase & architecture audit

Verified by reading every backend module, the test suite, the scripts, the
migrations, and the frontend. Line counts are from the original state.

## What the system actually does

```
PayPal Disputes API ──► CaseService.sync ──► Case + PayPalFact (revisioned)
PayPal webhooks ──────► PayPalEvent ──► WorkItem ──► worker ──► same sync path
Support transcripts ──► EvidenceService ──► EvidenceRevision + EvidenceSetRevision
                                   │
                                   ▼
                        build_analysis_bundle()  (frozen JSON snapshot)
                                   │
                                   ▼
                    AIReasoningProvider (OpenAI structured outputs)
                                   │
                                   ▼
                 validate_ai_output()  (deterministic graph compiler)
                                   │
                                   ▼
             SafetyService.assess()  (deterministic policy over the graph)
                                   │
                                   ▼
        ActionApproval (immutable payload + hashes) ──► ActionEngine.execute()
                                   │
                                   ▼
                     fresh PayPal GET → revalidate → one POST
                                   │
                                   ▼
           sync / UNKNOWN_OUTCOME → reconciliation (auto probe, manual release)
```

The design is unusually rigorous for a hackathon project. The parts that are
genuinely good, and that this cycle did not disturb:

- **Source typing is enforced, not documented.** `backend/casegraph/validate.py`
  rejects a `VERIFIED_FACT` whose statement is not byte-identical to the PayPal
  fact value, a claim whose excerpt is not a verbatim substring of the cited
  evidence revision, a claim whose speaker contradicts the evidence speaker, a
  duplicated contradiction pair, and any cycle among provenance edges.
- **The safety layer is model-independent.** `backend/safety/service.py` computes
  transitive grounding by walking `DERIVED_FROM/SUPPORTS/REFERENCES/CLAIMS`
  edges, then blocks ungrounded inferences, blocks high-risk actions supported by
  missing evidence, and degrades contradicted support to REVIEW or BLOCK
  depending on risk class.
- **Approval binds semantics, not just bytes.** `_assert_local_chain_current`
  re-verifies analysis → graph → safety → policy hash → case revision → evidence
  revision inside one transaction holding the case row lock.
- **Financial write discipline.** `UNKNOWN_OUTCOME` is preserved, never retried;
  `_mark_result` sets `post_action_sync_pending` before any post-write work.
- **Durable queue** with leases, bounded retry, backoff, dead-letter, and a
  per-dispute advisory lock that is not held across network I/O.

## Defects found

### D1 — Reconciliation module could never execute (critical)

`backend/work/reconciliation.py` was written against a different data model than
`backend/db/models.py`, `backend/work/domain.py`, and `backend/work/schemas.py`:

| Service expects | Model/schema actually had |
| --- | --- |
| `ActionReconciliation(resulting_execution_status=…)` | no such column |
| `row.details_json`, `row.details_hash`, `row.record_hash` | `detail_json`, `detail_hash`, no `record_hash` |
| `row.resulting_execution_status` | `before_status`, `after_status` |
| `ReconciliationMethod.AUTO_PAYPAL_STATE` | `AUTOMATIC` |
| `ReconciliationMethod.MANUAL_PAYPAL_DASHBOARD` | `MANUAL` |
| `ReconciliationOutcome.INCONCLUSIVE` | `STILL_AMBIGUOUS` |
| `ReconciliationResponse(action_uid=…, observed_snapshot_hash=…, details=…, execution_status=…)` | `before_status`, `after_status`, `detail` |
| `req.decision` | `ManualReconciliationRequest.outcome` |

Proven directly:

```
MODEL COLS: [... 'before_status', 'after_status', 'paypal_snapshot_hash', 'detail_json', 'detail_hash' ...]
RESP FIELDS: [... 'before_status', 'after_status', 'detail' ...]
CONSTRUCT ERROR: TypeError 'resulting_execution_status' is an invalid keyword argument for ActionReconciliation
```

Impact: an action left in `UNKNOWN_OUTCOME` blocks every subsequent write for that
case (`approval_repo.unresolved_for_case`). The only documented release valve —
manual reconciliation from the PayPal dashboard — raised `AttributeError` before
it could record anything. The case was permanently bricked.

Why the suite did not catch it: `tests/test_durable_workflow.py` asserted on the
*text* of `scripts/reconcile_action.py` (`"--confirm-paypal-dashboard" in source`)
and on route inventory, never on behaviour. This is the central lesson of the
audit: **source-text assertions are not tests.**

### D2 — Approval and execution were unusable over HTTP (critical)

```python
# backend/api/actions.py (before)
@router.post('/{case_id}/actions/approve',response_model=ActionApprovalResponse)
async def approve(case_id,req): return await action_engine.approve(case_id,req)
```

No annotations → FastAPI treats `req` as a required query parameter. Observed
against a live server:

```
Invoke-RestMethod : {"detail":[{"type":"missing","loc":["query","req"],
"msg":"Field required","input":null}]}
```

Impact: the product's central interaction — a human approving a payload — failed
for every browser user. Service-level tests called `action_engine` directly and
passed, so CI was green while the product was broken.

### D3 — Test suite could delete the developer's database (high)

`tests/action_fixtures.py` executes `create_all()` at import against
`settings.database_url`, and suites such as `tests/test_integration_contract.py`
use an autouse fixture running `Base.metadata.drop_all(engine)`. With the default
configuration that is `.data/casegraph.db` — the same database the running
application uses. Any `pytest` invocation destroyed local cases, evidence, and
approvals.

### D4 — OIDC key rotation produced 30 seconds of 401s (high)

`JWTVerifier` relied on `PyJWKClient.get_signing_key`, which refuses to refetch
the JWKS for an unknown `kid` while inside its `cooldown_duration` (30 s). A
provider rotating signing keys would have valid tokens rejected for up to 30 s.
Fix: an explicit, lock-guarded, rate-limited forced refresh (one per 5 s window)
when the `kid` is unknown.

### D5 — Integration gate could never pass (medium)

`scripts/integration_gate.py` asserted `expected != "20261025_0008"` while
`expected_head_revision()` returned `20261025_0009`. A second hard-coded literal
had drifted.

### D6 — Protocol lock was OS-dependent (medium)

`scripts/freeze_validation_protocol.py` stored `str(path.relative_to(ROOT))`,
producing backslashes on Windows. A lock frozen on Windows could not be verified
against POSIX artifact names.

## Structural observations

Resolved in cycle 2 (kept here so the audit history stays readable):

- **`list_cases` was N+1** — now `CaseService.list_details()` with a constant
  query count, and a test that asserts the count does not grow with cases.
- **No canonical explanation artifact** — now
  `GET …/ai/analyses/{uid}/explain`, deterministic and exportable.
- **No frontend error boundary** — added; a malformed payload no longer blanks
  the application.
- **Multipart timeout was a literal** — now `PAYPAL_MULTIPART_TIMEOUT_SECONDS`.

Still open:

- **Three overlapping "explain" surfaces.** The graph, the safety report, and the
  approval payload each describe part of the reasoning. The new export is the
  canonical artifact, but the graph and safety views still render their own
  framing rather than consuming it.
- **`paypal/http.py` creates a new `httpx.AsyncClient` per call.** No connection
  reuse. Under real load this is measurable; it was left alone because changing
  client lifecycle without a live PayPal run would be speculative. (The multipart
  *timeout* is now configurable, which is a separate concern.)
- **No retrieval layer.** The bundle is the entire case. That is correct for small
  disputes and will not scale to cases with hundreds of evidence revisions;
  FinRCA-Bench suggests typed traversal over the provenance graph is the right
  shape when that day comes.
- **Governance scaffolding is large relative to product surface.**
  `validation/`, `submission/`, `evaluation/` and their tests are ~35% of the
  tree. They are honest, but they are not what wins a product-design judging
  criterion.

## Frontend audit

Original state: one 72-line `App.tsx` (≈15 KB) containing the whole application,
with `JSON.stringify` dumps for the safety report and a raw `<textarea>` for the
action payload. The "graph" tab rendered seven vertical lists. No component
boundaries, no loading states, no per-node inspection, no visual distinction
between a verified fact and a model inference — for a product whose thesis *is*
provenance. The rewrite addresses this; see
[`07-implementation-changelog.md`](07-implementation-changelog.md).
