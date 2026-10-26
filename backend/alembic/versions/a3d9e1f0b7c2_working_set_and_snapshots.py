"""working set, Europe PMC ids, dedupe snapshots

Revision ID: a3d9e1f0b7c2
Revises: fc572bce6c80
Create Date: 2026-10-27 09:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3d9e1f0b7c2"
down_revision: Union[str, None] = "fc572bce6c80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "query_versions",
        sa.Column("source_hits", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "query_versions", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.execute("update query_versions set active = (status = 'fetched')")
    op.add_column("records", sa.Column("source_id", sa.String(length=60), nullable=True))
    op.create_unique_constraint("records_source_id_key", "records", ["source_id"])
    op.add_column("dedup_groups", sa.Column("run_id", sa.Integer(), nullable=True))
    op.create_foreign_key("dedup_groups_run_id_fkey", "dedup_groups", "run_log", ["run_id"], ["id"])
    op.create_index("ix_dedup_groups_run_id", "dedup_groups", ["run_id"])
    # Existing groups belong to the latest successful dedupe run, so they stay the current snapshot.
    op.execute(
        "update dedup_groups set run_id = "
        "(select max(id) from run_log where step = 'dedupe' and status = 'ok')"
    )


def downgrade() -> None:
    op.drop_index("ix_dedup_groups_run_id", table_name="dedup_groups")
    op.drop_constraint("dedup_groups_run_id_fkey", "dedup_groups", type_="foreignkey")
    op.drop_column("dedup_groups", "run_id")
    op.drop_constraint("records_source_id_key", "records", type_="unique")
    op.drop_column("records", "source_id")
    op.drop_column("query_versions", "active")
    op.drop_column("query_versions", "source_hits")
