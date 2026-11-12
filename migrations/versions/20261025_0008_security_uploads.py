"""Security hardening and immutable evidence-file metadata.

Revision ID: 20261025_0008
Revises: 20261025_0007
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261025_0008"
down_revision = "20261025_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "evidence_files" not in inspector.get_table_names():
        op.create_table(
            "evidence_files",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("file_uid", sa.String(length=64), nullable=False),
            sa.Column("case_id", sa.String(length=64), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("original_name", sa.String(length=512), nullable=False),
            sa.Column("storage_key", sa.String(length=256), nullable=False),
            sa.Column("detected_mime", sa.String(length=64), nullable=False),
            sa.Column("extension", sa.String(length=16), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("scan_status", sa.String(length=32), nullable=False),
            sa.Column("created_by", sa.String(length=256), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("scanner_detail", sa.Text()),
            sa.UniqueConstraint("file_uid", name="uq_evidence_files_uid"),
            sa.UniqueConstraint("storage_key", name="uq_evidence_files_storage_key"),
            sa.CheckConstraint("size_bytes > 0 AND size_bytes < 10000000", name="ck_evidence_files_paypal_size"),
            sa.CheckConstraint("scan_status IN ('CLEAN','UNSCANNED_DEV_ONLY')", name="ck_evidence_files_scan_status"),
            sa.CheckConstraint("detected_mime IN ('application/pdf','image/jpeg','image/png','image/gif')", name="ck_evidence_files_mime"),
        )
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("evidence_files")}
    if "ix_evidence_files_case_created" not in existing_indexes:
        op.create_index("ix_evidence_files_case_created", "evidence_files", ["case_id", "created_at"])
    if "ix_evidence_files_sha256" not in existing_indexes:
        op.create_index("ix_evidence_files_sha256", "evidence_files", ["sha256"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "evidence_files" not in inspector.get_table_names():
        return
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("evidence_files")}
    if "ix_evidence_files_sha256" in existing_indexes:
        op.drop_index("ix_evidence_files_sha256", table_name="evidence_files")
    if "ix_evidence_files_case_created" in existing_indexes:
        op.drop_index("ix_evidence_files_case_created", table_name="evidence_files")
    op.drop_table("evidence_files")
