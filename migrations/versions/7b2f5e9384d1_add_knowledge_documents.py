"""add knowledge documents

Revision ID: 7b2f5e9384d1
Revises: 6114d2b80bc6
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "7b2f5e9384d1"
down_revision = "6114d2b80bc6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("knowledge_document")
