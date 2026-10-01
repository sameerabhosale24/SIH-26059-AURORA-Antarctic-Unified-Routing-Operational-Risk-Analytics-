"""operational data tables

Adds the operational schema: vessel telemetry, AIS, icebergs, routes,
waypoints, alarms and the data_version ledger.

Three tables become TimescaleDB hypertables partitioned on ``ts``. Every
hypertable primary key includes the partition column because TimescaleDB
rejects a unique index that omits it.

Revision ID: 3f2a9c1d7e40
Revises: 986db58b4143
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = '3f2a9c1d7e40'
down_revision: Union[str, Sequence[str], None] = '986db58b4143'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POINT_4326 = Geometry(geometry_type='POINT', srid=4326, spatial_index=False)
POLYGON_4326 = Geometry(geometry_type='POLYGON', srid=4326, spatial_index=False)
LINESTRING_4326 = Geometry(geometry_type='LINESTRING', srid=4326, spatial_index=False)

HYPERTABLES = ('vessel_state', 'ais_track', 'iceberg_position')

DATA_VERSION_KEYS = (
    'sic', 'currents', 'weather', 'icebergs',
    'enc', 'ice_thickness', 'bathymetry',
)


def upgrade() -> None:
    op.create_table(
        'vessel_state',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('vessel_id', sa.BigInteger(), nullable=True),
        sa.Column('lat', sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column('lon', sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column('sog', sa.REAL(), nullable=True),
        sa.Column('cog', sa.REAL(), nullable=True),
        sa.Column('heading', sa.REAL(), nullable=True),
        sa.Column('rot', sa.REAL(), nullable=True),
        sa.Column('draft', sa.REAL(), nullable=True),
        sa.Column('ukc', sa.REAL(), nullable=True),
        sa.Column('fuel_remaining', sa.REAL(), nullable=True),
        sa.Column('engine_load', sa.REAL(), nullable=True),
        sa.Column('wind_speed', sa.REAL(), nullable=True),
        sa.Column('wind_dir', sa.REAL(), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id', 'ts'),
    )

    op.create_table(
        'ais_track',
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('mmsi', sa.BigInteger(), nullable=False),
        sa.Column('lat', sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column('lon', sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column('sog', sa.REAL(), nullable=True),
        sa.Column('cog', sa.REAL(), nullable=True),
        sa.Column('heading', sa.REAL(), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('ship_type', sa.Text(), nullable=True),
        sa.Column('destination', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('ts', 'mmsi'),
    )

    op.create_table(
        'iceberg_position',
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('iceberg_id', sa.Text(), nullable=False),
        sa.Column('geom', POINT_4326, nullable=True),
        sa.Column('length_km', sa.REAL(), nullable=True),
        sa.Column('drift_bearing', sa.REAL(), nullable=True),
        sa.Column('drift_speed_kt', sa.REAL(), nullable=True),
        sa.Column('source', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('ts', 'iceberg_id'),
    )

    op.create_table(
        'iceberg_drift_cone',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('iceberg_id', sa.Text(), nullable=True),
        sa.Column('run_ts', sa.DateTime(timezone=True), nullable=True),
        sa.Column('horizon_h', sa.Integer(), nullable=True),
        sa.Column('geom', POLYGON_4326, nullable=True),
        sa.Column('probability', sa.REAL(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'route_run',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('vessel_id', sa.BigInteger(), nullable=True),
        sa.Column('run_ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('input_version', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('vessel_state_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'route',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('route_run_id', sa.BigInteger(), nullable=True),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('geom', LINESTRING_4326, nullable=True),
        sa.Column('distance_nm', sa.REAL(), nullable=True),
        sa.Column('eta', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fuel_estimate_t', sa.REAL(), nullable=True),
        sa.Column('risk_score', sa.REAL(), nullable=True),
        sa.Column('is_recommended', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'waypoint',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('route_id', sa.BigInteger(), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=True),
        sa.Column('geom', POINT_4326, nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('eta', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'alarm',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('vessel_id', sa.BigInteger(), nullable=True),
        sa.Column('severity', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('geom', POINT_4326, nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('acked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acked_by', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'data_version',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('source_ts', sa.DateTime(timezone=True), nullable=True),
        sa.Column('staleness', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )

    # ------------------------------------------------------------------
    # Hypertables. Created before the secondary indexes so TimescaleDB
    # propagates every index to each chunk as it is created.
    # ------------------------------------------------------------------
    for table in HYPERTABLES:
        op.execute(
            f"SELECT create_hypertable('{table}', 'ts', "
            f"if_not_exists => TRUE, migrate_data => TRUE)"
        )

    # Time-first btree indexes — the access path for every chart query.
    op.create_index('ix_vessel_state_ts', 'vessel_state', ['ts'], postgresql_ops={'ts': 'DESC'})
    op.create_index('ix_vessel_state_vessel_id_ts', 'vessel_state',
                    ['vessel_id', 'ts'], postgresql_ops={'ts': 'DESC'})
    op.create_index('ix_ais_track_ts', 'ais_track', ['ts'], postgresql_ops={'ts': 'DESC'})
    op.create_index('ix_ais_track_mmsi_ts', 'ais_track',
                    ['mmsi', 'ts'], postgresql_ops={'ts': 'DESC'})
    op.create_index('ix_iceberg_position_ts', 'iceberg_position', ['ts'],
                    postgresql_ops={'ts': 'DESC'})
    op.create_index('ix_iceberg_position_iceberg_id_ts', 'iceberg_position',
                    ['iceberg_id', 'ts'], postgresql_ops={'ts': 'DESC'})

    # GIST on every geometry column.
    op.create_index('ix_iceberg_position_geom', 'iceberg_position', ['geom'],
                    postgresql_using='gist')
    op.create_index('ix_iceberg_drift_cone_geom', 'iceberg_drift_cone', ['geom'],
                    postgresql_using='gist')
    op.create_index('ix_route_geom', 'route', ['geom'], postgresql_using='gist')
    op.create_index('ix_waypoint_geom', 'waypoint', ['geom'], postgresql_using='gist')
    op.create_index('ix_alarm_geom', 'alarm', ['geom'], postgresql_using='gist')

    # Non-spatial lookups used by the panels and the optimizer.
    op.create_index('ix_iceberg_drift_cone_iceberg_id', 'iceberg_drift_cone', ['iceberg_id'])
    op.create_index('ix_route_run_vessel_id', 'route_run', ['vessel_id'])
    op.create_index('ix_route_run_run_ts', 'route_run', ['run_ts'])
    op.create_index('ix_route_route_run_id', 'route', ['route_run_id'])
    op.create_index('ix_waypoint_route_id', 'waypoint', ['route_id'])
    op.create_index('ix_alarm_ts', 'alarm', ['ts'])
    op.create_index('ix_alarm_vessel_id', 'alarm', ['vessel_id'])
    op.create_index('ix_alarm_type', 'alarm', ['type'])

    # Seed the ledger: every source starts at version 0 and stays there
    # until a real, successful ingest bumps it.
    rows = ',\n    '.join(
        f"('{key}', 0, now(), NULL, NULL, NULL)" for key in DATA_VERSION_KEYS
    )
    op.execute(
        "INSERT INTO data_version (key, version, updated_at, source_ts, staleness, notes)\n"
        f"    VALUES\n    {rows}\n"
        "    ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table('data_version')
    op.drop_table('alarm')
    op.drop_table('waypoint')
    op.drop_table('route')
    op.drop_table('route_run')
    op.drop_table('iceberg_drift_cone')
    # DROP TABLE on a hypertable also drops every chunk.
    op.drop_table('iceberg_position')
    op.drop_table('ais_track')
    op.drop_table('vessel_state')
