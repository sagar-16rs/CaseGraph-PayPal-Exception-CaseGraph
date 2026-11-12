# Database migrations

## Fresh installation

Run:

```bash
alembic upgrade head
```

The consolidated repository contains the current migration chain required for fresh installations.

## Historical databases

This repository was consolidated from an earlier development history. The migration identified as `20261025_0007` represents the cumulative pre-security baseline used by the consolidated release. Databases created from an older historical development branch should not be blindly stamped to this revision.

If you have an existing historical database:

1. Back up the database.
2. Record its current Alembic revision.
3. Migrate it through the original historical repository until it reaches the equivalent baseline.
4. Adopt this repository only after the schema matches the consolidated baseline.
5. Run `alembic upgrade head`.
6. Run `python scripts/doctor.py` and the full verification suite.

Do not manually edit `alembic_version` to bypass schema migrations.

## Current head

`20261108_0010` (`reconciliation_alignment`). `scripts/doctor.py`,
`scripts/operations_doctor.py`, `scripts/security_doctor.py` and
`scripts/integration_gate.py` all compare the live database against
`backend.db.migrations.expected_head_revision()`, which is the single source of
truth — do not hard-code the revision anywhere else.

## Why 0010 is conditional

Migration `20261025_0007` builds the schema from the *current* SQLAlchemy
metadata rather than from a frozen snapshot. On a fresh database the
reconciliation table therefore already has the columns `0010` introduces, so
`0010` inspects the live schema and only adds or drops what actually differs.
This keeps both fresh installs and pre-existing databases correct.

The change it applies: the reconciliation audit table previously declared
`before_status`, `after_status`, `paypal_snapshot_hash`, `detail_json` and
`detail_hash`, while `backend/work/reconciliation.py` used
`resulting_execution_status`, `observed_snapshot_hash`, `details_json`,
`details_hash` and `record_hash`. No code could ever have written a row in the
old shape, so the downgrade restores the columns as nullable rather than
pretending to restore data.

Verified: `alembic upgrade head` → `downgrade base` → `upgrade head` on a clean
SQLite database, and `scripts/doctor.py` reports `current == expected ==
20261108_0010`.
