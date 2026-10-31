"""candidate selection: a fair choice of successor among 2-4 candidates

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24 09:00:00

- handoff.successor_id is null while the handoff is 'selecting'; the admin's selection
  fills it and moves the handoff to 'active'.
- handoff.max_attempts bounds the assessed attempts each candidate gets per exercise.
- handoff_candidate: the pool, with the alias the expert sees while selecting.
- successor_selection: the decision, append-only (same trigger as knowledge_version).
- attempt_review: a learner's review request and the expert's criterion overrides. The
  attempt itself is never changed.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("handoff", "successor_id", existing_type=sa.Text(), nullable=True)
    op.add_column(
        "handoff",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
    )
    op.create_check_constraint("ck_handoff_status", "handoff", "status in ('selecting','active')")
    op.create_check_constraint(
        "ck_handoff_successor_when_active",
        "handoff",
        "status = 'selecting' or successor_id is not null",
    )
    op.create_check_constraint("ck_handoff_max_attempts", "handoff", "max_attempts >= 1")

    op.create_table(
        "handoff_candidate",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("handoff_id", sa.UUID(), sa.ForeignKey("handoff.id"), nullable=False),
        sa.Column("person_id", sa.Text(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("study_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_id", "person_id"),
        sa.UniqueConstraint("handoff_id", "alias"),
    )

    op.create_table(
        "successor_selection",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("handoff_id", sa.UUID(), sa.ForeignKey("handoff.id"), nullable=False),
        sa.Column("selected_person_id", sa.Text(), nullable=False),
        sa.Column("recommended", postgresql.JSONB(), nullable=False),
        sa.Column("in_recommended", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_id"),
    )
    op.execute(
        "create trigger successor_selection_immutable before update or delete "
        "on successor_selection for each row execute function sb_forbid_update();"
    )

    op.create_table(
        "attempt_review",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("attempt_id", sa.UUID(), sa.ForeignKey("attempt.id"), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("overrides", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        # One review per attempt.
        sa.UniqueConstraint("attempt_id"),
    )


def downgrade() -> None:
    op.drop_table("attempt_review")
    op.execute("drop trigger if exists successor_selection_immutable on successor_selection")
    op.drop_table("successor_selection")
    op.drop_table("handoff_candidate")
    op.drop_constraint("ck_handoff_max_attempts", "handoff", type_="check")
    op.drop_constraint("ck_handoff_successor_when_active", "handoff", type_="check")
    op.drop_constraint("ck_handoff_status", "handoff", type_="check")
    op.drop_column("handoff", "max_attempts")
    op.alter_column("handoff", "successor_id", existing_type=sa.Text(), nullable=False)
