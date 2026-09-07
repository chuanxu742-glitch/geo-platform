"""Durable bounded agent runs, checkpoints and immutable review decisions."""
from alembic import op
import sqlalchemy as sa

revision = 'a71d9b33e204'
down_revision = '9c371d04b221'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('goal', sa.Text(), nullable=False),
        sa.Column('policy', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('phase', sa.String(60), nullable=False),
        sa.Column('blocked_reason', sa.Text(), nullable=False),
        sa.Column('checkpoint', sa.JSON(), nullable=False),
        sa.Column('lease_owner', sa.String(100)),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('next_due', sa.DateTime(timezone=True)),
        sa.Column('parent_run_id', sa.Integer(), sa.ForeignKey('agent_runs.id'), unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('agent_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('agent_runs.id'), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('kind', sa.String(60), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('output', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('run_id', 'key'))
    op.create_table('agent_approvals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('agent_runs.id'), nullable=False),
        sa.Column('proposal_id', sa.Integer(), sa.ForeignKey('agent_steps.id'), nullable=False, unique=True),
        sa.Column('decision', sa.String(30), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=False),
        sa.Column('reviewer', sa.String(200), nullable=False),
        sa.Column('allow_publish', sa.Boolean(), nullable=False),
        sa.Column('bindings', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_agent_runs_claim', 'agent_runs', ['status', 'lease_until'])


def downgrade():
    op.drop_table('agent_approvals')
    op.drop_table('agent_steps')
    op.drop_table('agent_runs')
