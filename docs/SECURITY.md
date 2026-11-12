# Security

## Authentication and authorization

Production uses OIDC-compatible JWT authentication. Tokens are validated for issuer, audience, signature algorithm, expiry, subject, and configured tenant claim. JWKS deployments constrain the JWKS host to the configured issuer host.

Supported roles are `VIEWER`, `ANALYST`, `APPROVER`, and `ADMIN`. Route authorization is enforced in the backend; frontend visibility is never treated as authorization.

## Tenant model

The current deployment model is one merchant tenant per deployment. An authenticated token's tenant claim must match the configured deployment tenant. This avoids pretending that a single PayPal credential set is safe multi-tenant routing.

## Approval integrity

Consequential actions are approved as immutable typed payloads. The approval record binds payload, graph, safety, analysis, and policy hashes. Execution cannot replace the reviewed payload.

## Remote-write ambiguity

Potentially non-idempotent PayPal writes fail closed:

- confirmed response: `EXECUTED`
- definite request rejection: `FAILED`
- timeout/network/ambiguous server failure: `UNKNOWN_OUTCOME`

`UNKNOWN_OUTCOME` prevents blind replay until reconciliation completes.

## Evidence uploads

Uploads are validated by size, extension, detected file signature, and malware-scanning policy. Bytes are stored under randomized internal names outside the public frontend. SHA-256 is recorded and rechecked when approved files are used in PayPal actions.

## Rate limiting and resource controls

Production requires Redis-backed rate limiting. Buckets are keyed by authenticated subject and route class so rotating case identifiers cannot evade controls. Production is configured to fail closed if the required rate-limit backend is unavailable.

## Webhooks

Production requires PayPal webhook verification and a configured webhook identifier. Webhook events are persisted and deduplicated before durable processing.

## Browser security

The frontend uses Authorization Code + PKCE when OIDC is enabled. Production origins are explicit HTTPS origins. API documentation is disabled in production.

## Secrets

Never commit `.env`, OAuth client secrets, API keys, bearer tokens, private keys, study participant data, uploaded evidence, or runtime databases. Run `python scripts/release_scan.py` before every public release.
