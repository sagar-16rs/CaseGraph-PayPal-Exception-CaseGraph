# Operations

## API

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Health endpoints:

```text
GET /health
GET /ready
```

## Worker

```bash
python scripts/worker.py
```

For diagnostics:

```bash
python scripts/worker.py --once
python scripts/operations_doctor.py
```

## Reconciliation

Use the operator reconciliation CLI only after manually verifying an ambiguous action in the PayPal dashboard. The public API does not expose an unauthenticated manual ambiguity override.

```bash
python scripts/reconcile_action.py --help
```

## Diagnostics

```bash
python scripts/doctor.py
python scripts/security_doctor.py
python scripts/integration_doctor.py
```

## Live integration gate

`integration_gate.py` performs controlled checks for production dependencies such as PostgreSQL, Redis, OIDC/JWKS, ClamAV, OpenTelemetry, frontend build tooling, and read-only PayPal sandbox access. Real PayPal file writes are intentionally handled by a separate explicitly confirmed gate.

```bash
python scripts/integration_gate.py --help
python scripts/paypal_file_gate.py --help
```

## Backups

Back up PostgreSQL and the private evidence volume together. Uploaded file metadata without the corresponding private file bytes is insufficient to reconstruct evidence history.
