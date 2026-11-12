"""Cumulative pre-security schema baseline.

Revision ID: 20261025_0007
Revises: None

The original historical migration chain is not byte-exportable from the retained
artifact archive used to consolidate this repository. This migration therefore
serves as the explicit cumulative baseline for all durable tables that existed
before the security upload layer. The evidence-file table is intentionally created only by
0008 so PostgreSQL foreign-key ordering remains valid.
"""
from alembic import op

from backend.db.base import Base
from backend.db import models  # noqa: F401  - registers pre-security tables

revision = "20261025_0007"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
