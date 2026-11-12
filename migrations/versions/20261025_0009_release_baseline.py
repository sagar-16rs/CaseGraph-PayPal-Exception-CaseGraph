"""Release schema marker.

Revision ID: 20261025_0009
Revises: 20261025_0008

All current tables are created by the cumulative pre-security baseline (0007)
and the security evidence-file migration (0008). This revision deliberately has
no DDL so downgrade ordering remains safe: 0008 removes evidence_files before
0007 removes the referenced cases table.
"""
revision = "20261025_0009"
down_revision = "20261025_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
