"""Question deadline, and one team per name in a session.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("game_sessions", sa.Column("question_deadline", sa.Float(), nullable=True))
    op.create_index(
        "uq_team_session_name_ci",
        "teams",
        ["session_id", sa.text("lower(team_name)")],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_team_session_name_ci", table_name="teams")
    op.drop_column("game_sessions", "question_deadline")
