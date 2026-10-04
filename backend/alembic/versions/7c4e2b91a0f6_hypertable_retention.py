"""hypertable compression and retention

The two telemetry hypertables only ever get written to and read by time
range, which is exactly the shape TimescaleDB compresses well. This
migration turns compression on and gives each table a retention window so
the deployment stops growing without bound on a disk nobody is watching.

The windows are deliberately different:

* ``vessel_state`` — the own-ship track. Long, because an incident review
  months later still needs to know where the ship was, and cheap, because
  segmenting by ``vessel_id`` compresses a slow-moving hull's telemetry
  into almost nothing.
* ``ais_track`` — everybody else's positions. Short, because a contact
  from three weeks ago is not traffic, it is history, and it is by far the
  chattiest of the two.

They are written here rather than read from configuration because a
retention policy is a property of the stored data: changing it is a
migration, not an environment variable, so the same database always
enforces the same window regardless of what any process was started with.

Revision ID: 7c4e2b91a0f6
Revises: 3f2a9c1d7e40
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7c4e2b91a0f6'
down_revision: Union[str, Sequence[str], None] = '3f2a9c1d7e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Compression window and segment key per hypertable.
COMPRESSION = (
    ('vessel_state', 'vessel_id', '7 days'),
    ('ais_track', 'mmsi', '7 days'),
)

#: Retention window per hypertable.
RETENTION = (
    ('vessel_state', '180 days'),
    ('ais_track', '30 days'),
)


def upgrade() -> None:
    # Compression must be enabled on the hypertable before a policy can be
    # attached to it; the segment key is what makes a chunk compressible,
    # and it has to be a column that is not the time dimension.
    for table, segmentby, after in COMPRESSION:
        op.execute(
            f"ALTER TABLE {table} SET ("
            f"timescaledb.compress, "
            f"timescaledb.compress_segmentby = '{segmentby}')"
        )
        op.execute(f"SELECT add_compression_policy('{table}', INTERVAL '{after}')")

    for table, window in RETENTION:
        op.execute(f"SELECT add_retention_policy('{table}', INTERVAL '{window}')")


def downgrade() -> None:
    # Policies first: a compression policy cannot be removed from a table
    # that is no longer compressible, and neither policy is wanted once the
    # table is back to plain storage.
    for table, _window in RETENTION:
        op.execute(f"SELECT remove_retention_policy('{table}', if_exists => TRUE)")
    for table, _segmentby, _after in COMPRESSION:
        op.execute(f"SELECT remove_compression_policy('{table}', if_exists => TRUE)")

    # Compression itself is left switched on. Turning it off would fail on
    # any chunk that has already been compressed, and those chunks hold real
    # data — a downgrade must not be able to destroy the telemetry it was
    # asked to stop compressing.
