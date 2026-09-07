"""Add project-scoped imported measurements and provenance."""
from alembic import op
import sqlalchemy as sa

revision = "b82e4c65f901"
down_revision = "a71d9b33e204"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("measurements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source_label", sa.String(200), nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=True),
        sa.Column("clicks", sa.BigInteger(), nullable=True),
        sa.Column("leads", sa.BigInteger(), nullable=True),
        sa.Column("orders", sa.BigInteger(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_measurements_project_fingerprint"))
    op.create_index("ix_measurements_project_id", "measurements", ["project_id"])


def downgrade():
    op.drop_index("ix_measurements_project_id", table_name="measurements")
    op.drop_table("measurements")
