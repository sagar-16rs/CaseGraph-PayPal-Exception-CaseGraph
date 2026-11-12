# Testing

## Deterministic local verification

Linux/macOS:

```bash
./scripts/verify.sh
```

Windows PowerShell:

```powershell
.\scripts\verify.ps1
```

The verifier compiles Python, exercises Alembic upgrade/downgrade/re-upgrade on a clean database, runs repository diagnostics, executes tests in isolated files, performs the release secret scan, and runs the offline TypeScript smoke check when `tsc` is available.

### Database isolation

`tests/conftest.py` binds the suite to a per-process SQLite file under `.data/`
(`sqlite:///./.data/pytest-<pid>.db`) unless `DATABASE_URL` is already set. This
matters: several suites call `Base.metadata.drop_all(engine)` in autouse fixtures,
and they previously resolved to `.data/casegraph.db` — the same database a running
development server uses. A plain `pytest` invocation could therefore destroy local
cases and evidence. Set `DATABASE_URL` explicitly to point tests at any other
isolated database (CI does this).

## Test areas

- action approval and execution safety, including the HTTP surface
  (`tests/test_http_journey.py`)
- automatic and manual reconciliation, including the manual-confirmation gate
  (`tests/test_reconciliation.py`)
- the simulated PayPal transport and the end-to-end journey without credentials
  (`tests/test_demo_simulation.py`)
- durable work queue and reconciliation
- benchmark methodology and scoring
- OIDC/JWT and authorization
- rate limiting
- secure evidence uploads
- file/action hash integrity
- JWKS rotation
- OpenTelemetry probe
- frontend/backend contracts and the graph renderer
- controlled validation-study methodology
- public release and submission checks

## External gates

The following require a real environment and cannot be proven by unit tests alone:

- PostgreSQL concurrency
- Redis authentication and fail-closed behavior
- real OIDC login and JWKS rotation
- ClamAV signatures and EICAR detection
- OpenTelemetry collector export
- frontend dependency installation and production build
- live OpenAI structured output
- PayPal sandbox OAuth, disputes, webhooks, actions, and file evidence
- real controlled user study if quantitative user-benefit claims are made
