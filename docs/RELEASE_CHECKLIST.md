# Release checklist

A release is not production-verified until both deterministic tests and external integration gates pass.

## Code and database

- full verification suite passes
- Alembic upgrade/downgrade/re-upgrade passes on a clean database
- production database is PostgreSQL and at migration head
- release secret scan passes
- no runtime/cache/build artifacts are committed

## Security

- OIDC login works with the real issuer
- issuer, audience, tenant, roles, and JWKS validation are confirmed
- Redis rate limiting works and fails closed
- ClamAV detects the EICAR test file with fresh signatures
- browser origins are explicit HTTPS origins
- PayPal webhooks are verified

## External services

- OpenTelemetry trace reaches the configured collector
- OpenAI structured-output path succeeds
- PayPal sandbox dispute read/sync works
- at least one explicitly approved sandbox action succeeds
- PayPal file-evidence path succeeds if used by the demo

## Frontend

- dependency installation succeeds
- lockfile is committed
- typecheck passes
- production build passes
- dependency audit has no unresolved high-severity issue

## Public release

- license is chosen and added
- `.env`, uploaded evidence, participant data, private evaluation runs, and credentials are excluded
- public release ZIP verifies against its manifest
- public repository and demo URLs contain no placeholders
