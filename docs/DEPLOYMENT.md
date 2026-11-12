# Deployment

## Production requirements

Use PostgreSQL, authenticated Redis, OIDC/JWKS, ClamAV, explicit HTTPS frontend origins, verified PayPal webhooks, and an OpenTelemetry collector.

Copy `.env.production.example` to your secret-management system and replace every placeholder. Do not commit the populated file.

## Containers

`deploy/compose.production.yml` is an example topology containing API, worker, PostgreSQL, Redis, ClamAV signature updater, and OpenTelemetry collector services.

```bash
docker compose -f deploy/compose.production.yml up --build
```

The example should be adapted to your infrastructure and secret manager before public deployment.

## Database

Run migrations before starting production API/worker processes:

```bash
alembic upgrade head
```

Production startup checks the actual Alembic revision and refuses a stale database.

## Frontend

Build with production OIDC configuration from `frontend/.env.production.example`.

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

Commit a generated `package-lock.json` once dependency installation succeeds in your environment and use `npm ci` thereafter.
