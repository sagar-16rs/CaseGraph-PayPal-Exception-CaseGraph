# Verification record

Release candidate: `1.0.0-rc2`

This record covers the local, deterministic verification performed for the
`1.0.0-rc2` submission candidate. It supersedes the `1.0.0-rc1` record. The
research-cycle detail — including the defects that motivated this round — lives
in [`../research/aris-casegraph-audit/08-verification-record.md`](../research/aris-casegraph-audit/08-verification-record.md).

## Verified locally

- Python compilation succeeds for `backend`, `evaluation`, `validation`,
  `submission`, `scripts`, `tests`, `migrations`.
- Alembic upgrade → downgrade → re-upgrade succeeds on a clean SQLite database
  as well as on pre-initialized databases; head is `20261108_0010`.
- Repository doctor (`scripts/doctor.py`) reports `PASS` with head `20261108_0010`
  and all required tables.
- Security doctor (`scripts/security_doctor.py`), integration doctor
  (`scripts/integration_doctor.py`), benchmark doctor
  (`scripts/benchmark_doctor.py --require-casegraph`), validation doctor
  (`scripts/validation_doctor.py`), and submission doctor
  (`scripts/submission_doctor.py --repo .`) all report `PASS`, and operations
  doctor (`scripts/operations_doctor.py`) reports `LOCAL_PASS_POSTGRES_PENDING`
  (exit 0).
- **212 deterministic Python tests pass, 0 fail, 0 skip.** The suite binds itself
  to an isolated per-process database (`tests/conftest.py`) and removes it on exit,
  so running `pytest` never touches `.data/casegraph.db` or leaves stale files behind.
- Behavioural coverage includes:
  - `tests/test_http_journey.py` driving the ASGI app end to end (including the
    audit-explanation export);
  - `tests/test_reconciliation.py` executing automatic and manual reconciliation;
  - `tests/test_demo_simulation.py` exercising the simulated PayPal transport,
    including an injected `UNKNOWN_OUTCOME` and its release path;
  - `tests/test_explanations.py` and `tests/test_readiness.py` covering the
    deterministic explanation artifact, dispute readiness, negation handling, and
    constant-query case board projection;
  - `tests/test_ai_providers.py` verifying both the OpenAI `/v1/responses` path
    and the `/v1/chat/completions` adapter (DeepSeek / OpenAI-compatible gateways).
- Frontend TypeScript typecheck passes and the production Vite build succeeds.
- Release secret scan (`scripts/release_scan.py`), cross-platform manifest check
  (`scripts/regenerate_manifest.py --check`), and public release builder/verifier
  (`scripts/build_public_release.py` + `scripts/verify_public_release.py`) all
  report `PASS`.

## Not verified locally

Production readiness additionally requires the environment-specific checks
documented in [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md):

- PostgreSQL concurrency and the advisory-lock path (no PostgreSQL instance).
- Redis-backed rate limiting.
- OIDC/JWKS against a real identity provider.
- ClamAV malware scanning.
- OpenTelemetry export.
- A full live PayPal **sandbox** dispute lifecycle (OAuth and webhook registration
  were verified against the sandbox API; end-to-end dispute mutation requires a
  sandbox dispute on the account).
- A live model call through `CASEGRAPH_AI_PROVIDER=openai|deepseek` with a live API key.
