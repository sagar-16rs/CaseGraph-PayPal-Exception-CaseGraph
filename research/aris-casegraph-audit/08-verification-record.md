# Verification record

All results below were produced in this session. Commands are PowerShell; the
virtual environment is `.venv` (Python 3.14.5, Node 24.15.0). Where a result
differs between the agent sandbox and a normal shell, both are given.

## Test suite

| Run | Conditions | Result |
| --- | --- | --- |
| Baseline | sandbox, default `.data` database | `84 passed, 3 failed, 30 errors` |
| Baseline | sandbox, isolated `DATABASE_URL` | `99 passed, 1 failed, 17 errors` |
| After cycle 1 | sandbox, isolated `DATABASE_URL` | `116 passed, 1 warning, 17 errors` |
| After cycle 1 | normal shell (full file access) | `133 passed, 1 warning` |
| After cycle 2 | normal shell, default settings | `143 passed, 1 warning in 29.43s` |
| **After cycle 3** | **normal shell, default settings** | **`147 passed, 1 warning`** |

The 17 sandbox errors were `PermissionError` from pytest's temporary-directory
factory, not product failures: they disappeared once the same suite ran with
normal file access. The one baseline failure was
`tests/test_oidc_rotation.py::test_jwks_client_refreshes_when_new_kid_appears`,
which is a real defect and is now fixed.

New coverage added this cycle:

- `tests/test_http_journey.py` — 4 tests through the ASGI app.
- `tests/test_reconciliation.py` — 6 tests executing the reconciliation paths.
- `tests/test_demo_simulation.py` — 6 tests on the simulated end-to-end journey.
- `tests/test_explanations.py` — 8 tests on the explanation artifact and the
  batched case-board projection, including a query-count assertion.

## Database

```
$env:DATABASE_URL='sqlite:///./research/.tmp/alembic-test.db'
python -m alembic upgrade head      # 0007 -> 0008 -> 0009 -> 0010
python -m alembic downgrade base    # 0010 -> ... -> (empty)
python -m alembic upgrade head      # replay clean
python scripts/doctor.py            # PASS, current == expected == 20261108_0010
```

`scripts/doctor.py`: PASS — db_connectivity, required_tables, alembic_head,
security_configuration, paypal_sandbox_url all true; `missing_tables: []`.

`scripts/security_doctor.py`: PASS (development profile).

`scripts/operations_doctor.py`: PASS — queue tables present, revision
`20261108_0010`, empty queue.

## Static analysis and build

```
python -m compileall -q backend evaluation validation submission scripts tests migrations
    -> exit 0   (requires PYTHONPYCACHEPREFIX because migrations/versions/__pycache__
                  is not sandbox-writable; not a code failure)

cd frontend; npx tsc --noEmit
    -> exit 0

cd frontend; npx vite build
    -> dist/index.html                 0.34 kB
       dist/assets/index-*.css        15.82 kB  (gzip 3.85 kB)
       dist/assets/index-*.js        279.72 kB  (gzip 85.43 kB)
       built in 397 ms
```

## Visual verification (cycle 3)

Headless Chrome 157 was available on PATH, so the interface was rendered and
inspected rather than assumed. Loop: seed demo data → run API + Vite → screenshot
→ inspect → fix → repeat (nine iterations).

```
chrome --headless --disable-gpu --hide-scrollbars \
       --window-size=1512,982 --virtual-time-budget=9000 \
       --screenshot=<out>.png "http://127.0.0.1:5173/?view=<view>"
```

Captures retained in `figures/` (`ui-overview`, `ui-graph`, `ui-ai`, `ui-actions`,
`ui-1280`). Defects this loop caught and that a build check would not have:
a CSS grid declaring two rows for three children (the command bar expanded to
fill the viewport), graph columns vertically centred so they misaligned, and
internal fact enums rendered as node titles.

**Not covered:** interactive states (hover, focus rings, in-form validation, the
view transition) were not exercised by automation, and colour contrast was
reasoned from token values rather than measured with an audit tool.

Cycle 2 additions verified by the same commands: the explanation export is
reached through the ASGI app (`/explain` returns 200 with grounding, confidence and
next step; 404 for an unknown analysis), and the case board returns every case with
its facts from a constant number of queries.

## Live HTTP journey (simulated PayPal transport)

Server: `uvicorn backend.main:app --port 8022`, `CASEGRAPH_PAYPAL_TRANSPORT=simulated`,
`CASEGRAPH_AI_PROVIDER=rules`, isolated SQLite database, fresh simulator state.

```
demo_seed.py --reset-simulation
  analysis: COMPLETED graph=CASE-5F4111B4D34F6EE34EFB-R1   (PP-D-DEMO-1001)
  analysis: COMPLETED graph=CASE-FE4E0D6C4EA97860C37A-R1   (PP-D-DEMO-1002)
  analysis: COMPLETED graph=CASE-F3ED4579F0C82133EECA-R1   (PP-D-DEMO-1003)

GET  /api/cases
  CASES: PP-D-DEMO-1003 | PP-D-DEMO-1002 | PP-D-DEMO-1001   (simulated=true)

GET  /api/cases/{id}/ai/analyses
GET  /api/cases/{id}/ai/analyses/{aid}/safety
  SAFETY: REVIEW  recommended=SEND_MESSAGE  effective=SEND_MESSAGE  risk=LOW
  findings: ACTION_SUPPORT_IS_CONTRADICTED/REVIEW

POST /api/cases/{id}/actions/approve   (JSON body)
  APPROVAL: status=NOT_STARTED  hash=f45a072b058a…

POST /api/cases/{id}/actions/{uid}/execute  {"approval_hash": …}
  EXECUTION: EXECUTED / executed  dispute=WAITING_FOR_SELLER_RESPONSE

GET  /api/cases/{id}/graphs/latest
  GRAPH: CASE-5F4111B4D34F6EE34EFB-R1  nodes=14  edges=10  stale=True
```

`stale=True` after the write is correct: the simulated message changed the PayPal
payload, so the case revision advanced past the graph's input revision.

Before the annotation fix, the same call returned
`422 {"detail":[{"type":"missing","loc":["query","req"],"msg":"Field required"}]}`.
That contrast is the evidence that D2 was real and is closed.

## Security and submission gates

```
python scripts/release_scan.py
  status: FAIL, forbidden_source_files: [".env"]
```

This is the expected local result: the developer's `.env` exists and must never be
published. The public-release pipeline (`scripts/build_public_release.py`)
constructs a sanitized archive; this scan is a pre-publication guard, so a clean
run requires an `.env`-free checkout. No secret-like content was found in any
source file (`secret_like_findings: []`).

```
python scripts/submission_doctor.py --repo .
  rules_snapshot      true
  claim_ledger        true
  validation_framework true
  readme              true
  demo_mode           true          <- now "source" instead of an unset hosted URL
  hosted_demo_url     true
  video_duration      true
  secret_scan         false         <- .env present (see above)
  open_source_license false         <- BLOCKING: owner decision
  license_declared    false         <- BLOCKING: owner decision
  repo_url            false         <- BLOCKING: owner action
  video_url           false         <- BLOCKING: owner action
  status: FAIL
```

## Not verified

Stated plainly so nobody mistakes absence of a failure for success:

- **Live PayPal sandbox** — no credentials, not attempted.
- **Live OpenAI provider** — no key, not attempted.
- **PostgreSQL, Redis, OIDC, ClamAV, OpenTelemetry, Docker Compose** — infrastructure
  not available; `docs/RELEASE_CHECKLIST.md` remains the gate.
- **Browser rendering** — no browser automation available. Frontend assurance is
  typecheck, production build, contract tests, and the server-side journey.
- **User-validation study** — no participants; the repository's own tooling
  correctly reports `user_study_status: PENDING`.
