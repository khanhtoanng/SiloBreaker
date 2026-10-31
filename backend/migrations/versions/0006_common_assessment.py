"""successor selection phase 2: unassigned handoffs, common assessment, top snapshot

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24 15:00:00

- handoff.status gains 'unassigned': created without a successor ("choose later"). From
  there the admin assigns one directly or starts a common assessment ('selecting').
- handoff.assessment_exercise_id / assessment_due_at / assessment_started_at: the one released
  exercise every candidate answers, and its due time.
- successor_selection.top_ids / tie / is_top: snapshot of the score-based top the decision was
  made against. Null on phase-1 rows; recommended / in_recommended are kept as they were.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_handoff_successor_when_active", "handoff", type_="check")
    op.drop_constraint("ck_handoff_status", "handoff", type_="check")
    op.create_check_constraint(
        "ck_handoff_status", "handoff", "status in ('unassigned','selecting','active')"
    )
    op.create_check_constraint(
        "ck_handoff_successor_when_active",
        "handoff",
        "status in ('unassigned','selecting') or successor_id is not null",
    )
    op.add_column(
        "handoff",
        sa.Column("assessment_exercise_id", sa.UUID(), sa.ForeignKey("exercise.id"), nullable=True),
    )
    op.add_column(
        "handoff", sa.Column("assessment_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "handoff", sa.Column("assessment_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("successor_selection", sa.Column("top_ids", postgresql.JSONB(), nullable=True))
    op.add_column("successor_selection", sa.Column("tie", sa.Boolean(), nullable=True))
    op.add_column("successor_selection", sa.Column("is_top", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("successor_selection", "is_top")
    op.drop_column("successor_selection", "tie")
    op.drop_column("successor_selection", "top_ids")
    op.drop_column("handoff", "assessment_started_at")
    op.drop_column("handoff", "assessment_due_at")
    op.drop_column("handoff", "assessment_exercise_id")
    op.drop_constraint("ck_handoff_successor_when_active", "handoff", type_="check")
    op.drop_constraint("ck_handoff_status", "handoff", type_="check")
    op.create_check_constraint("ck_handoff_status", "handoff", "status in ('selecting','active')")
    op.create_check_constraint(
        "ck_handoff_successor_when_active",
        "handoff",
        "status = 'selecting' or successor_id is not null",
    )
