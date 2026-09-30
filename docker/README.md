# AURORA infrastructure

PostgreSQL 16 (TimescaleDB HA image) + Redis 7 for AURORA.

## Commands

```sh
docker compose up -d        # start both services
docker compose ps           # status (wait for "healthy")
docker compose down         # stop, keep data
docker compose down -v      # stop and WIPE all data
docker compose logs -f postgres
docker compose exec postgres psql -U aurora -d aurora
```

## Connection strings

| Service  | URL |
|----------|-----|
| Postgres | `postgresql+asyncpg://aurora:aurora@localhost:5432/aurora` |
| Postgres (psql) | `postgresql://aurora:aurora@localhost:5432/aurora` |
| Redis    | `redis://localhost:6379/0` |

## Extensions

Loaded by `docker/init/01-extensions.sql` on first database creation:

- `postgis`
- `timescaledb`
- `pg_stat_statements`
- `pg_trgm`

Verify with `docker compose exec postgres psql -U aurora -d aurora -c "\dx"`.

> Note: the init scripts only run when the data volume is empty. After
> `docker compose down -v`, the next `docker compose up -d` re-creates the
> database and re-runs them.
