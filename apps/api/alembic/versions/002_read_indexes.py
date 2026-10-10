"""Index project/time reads, agent previews, and pending background work."""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_runs_project_start", "runs", ["project_id", "started_at"]),
    ("ix_runs_agent_start", "runs", ["agent_id", "started_at"]),
    ("ix_runs_status", "runs", ["status"]),
    ("ix_incidents_agent_created", "incidents", ["agent_id", "created_at"]),
    ("ix_incidents_run", "incidents", ["run_id"]),
    ("ix_incidents_project_status", "incidents", ["project_id", "status"]),
    ("ix_investigations_status", "investigations", ["status"]),
)


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
