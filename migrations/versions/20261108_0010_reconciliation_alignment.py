"""Align the reconciliation audit table with the reconciliation service.

Revision ID: 20261108_0010
Revises: 20261025_0009

The reconciliation audit table was created from an earlier draft of the design
while `backend/work/reconciliation.py` was written against a later one: the
service constructs rows with `resulting_execution_status`, `details_json`,
`details_hash` and `record_hash`, none of which existed. Any auto or manual
reconciliation therefore raised `TypeError`, which meant an action left in
`UNKNOWN_OUTCOME` could never be resolved and the case stayed permanently
blocked from further PayPal writes.

This revision makes the persisted schema match the service. It is written to be
idempotent because migration `20261025_0007` builds the schema from the current
SQLAlchemy metadata: on a fresh database the correct columns already exist, so
the upgrade is a no-op there, while databases created from the old metadata are
altered in place.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261108_0010"
down_revision = "20261025_0009"
branch_labels = None
depends_on = None

_TABLE = "action_reconciliations"

_ADD = {
    "resulting_execution_status": sa.Column(
        "resulting_execution_status", sa.String(length=32), nullable=False, server_default=""
    ),
    "observed_snapshot_hash": sa.Column("observed_snapshot_hash", sa.String(length=64), nullable=True),
    "details_json": sa.Column("details_json", sa.JSON(), nullable=True),
    "details_hash": sa.Column("details_hash", sa.String(length=64), nullable=False, server_default=""),
    "record_hash": sa.Column("record_hash", sa.String(length=64), nullable=False, server_default=""),
}

_OBSOLETE = ("before_status", "after_status", "paypal_snapshot_hash", "detail_json", "detail_hash")


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def upgrade() -> None:
    if _TABLE not in sa.inspect(op.get_bind()).get_table_names():
        # Fresh installs create the table from current metadata; nothing to align.
        return
    existing = _columns()
    for name, column in _ADD.items():
        if name not in existing:
            op.add_column(_TABLE, column)
    for name in _OBSOLETE:
        if name in existing:
            op.drop_column(_TABLE, name)


def downgrade() -> None:
    if _TABLE not in sa.inspect(op.get_bind()).get_table_names():
        return
    existing = _columns()
    for name, column in _ADD.items():
        if name in existing:
            op.drop_column(_TABLE, name)
    # Restoring the obsolete shape cannot recover audit rows: the pre-fix module
    # crashed before persisting any. Re-added columns are nullable so the
    # downgrade remains safe on a populated table.
    legacy = {
        "before_status": sa.Column("before_status", sa.String(length=32), nullable=True),
        "after_status": sa.Column("after_status", sa.String(length=32), nullable=True),
        "paypal_snapshot_hash": sa.Column("paypal_snapshot_hash", sa.String(length=64), nullable=True),
        "detail_json": sa.Column("detail_json", sa.JSON(), nullable=True),
        "detail_hash": sa.Column("detail_hash", sa.String(length=64), nullable=True),
    }
    for name, column in legacy.items():
        if name not in existing:
            op.add_column(_TABLE, column)
