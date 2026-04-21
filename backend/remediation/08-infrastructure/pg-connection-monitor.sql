-- 08-infrastructure/pg-connection-monitor.sql
--
-- Writes a connection-stats row every minute. Grafana queries this for
-- saturation alerts. If you don't have pg_cron, wire it up as a Railway Cron
-- job calling this SQL file.
--
-- Apply once via Alembic migration or psql:
--   psql $DATABASE_URL -f pg-connection-monitor.sql

CREATE TABLE IF NOT EXISTS connection_stats (
    id            BIGSERIAL PRIMARY KEY,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total         INTEGER NOT NULL,
    active        INTEGER NOT NULL,
    idle          INTEGER NOT NULL,
    idle_in_tx    INTEGER NOT NULL,
    waiting       INTEGER NOT NULL,
    max_conns     INTEGER NOT NULL,
    saturation    NUMERIC(5, 2) NOT NULL  -- percentage
);

CREATE INDEX IF NOT EXISTS ix_connection_stats_collected_at
    ON connection_stats (collected_at DESC);

-- Retention: keep 30 days of per-minute stats.
-- Run manually or via pg_cron:
--   DELETE FROM connection_stats WHERE collected_at < NOW() - INTERVAL '30 days';

-- The collector — either call this via pg_cron every minute, or wrap it in a
-- stored procedure triggered by Railway cron.

CREATE OR REPLACE FUNCTION record_connection_stats() RETURNS void AS $$
DECLARE
    v_max INTEGER;
    v_total INTEGER;
    v_active INTEGER;
    v_idle INTEGER;
    v_idle_in_tx INTEGER;
    v_waiting INTEGER;
BEGIN
    SELECT setting::INTEGER INTO v_max FROM pg_settings WHERE name = 'max_connections';

    SELECT
        count(*) FILTER (WHERE state IS NOT NULL),
        count(*) FILTER (WHERE state = 'active'),
        count(*) FILTER (WHERE state = 'idle'),
        count(*) FILTER (WHERE state = 'idle in transaction'),
        count(*) FILTER (WHERE wait_event IS NOT NULL)
    INTO v_total, v_active, v_idle, v_idle_in_tx, v_waiting
    FROM pg_stat_activity
    WHERE backend_type = 'client backend';

    INSERT INTO connection_stats (
        total, active, idle, idle_in_tx, waiting, max_conns, saturation
    )
    VALUES (
        v_total,
        v_active,
        v_idle,
        v_idle_in_tx,
        v_waiting,
        v_max,
        ROUND(100.0 * v_total / NULLIF(v_max, 0), 2)
    );
END;
$$ LANGUAGE plpgsql;

-- pg_cron schedule (if extension available on your Railway plan):
-- SELECT cron.schedule('record_connection_stats', '* * * * *', $$SELECT record_connection_stats()$$);

-- Alert query — fire if sustained >70% for 5 minutes:
-- SELECT avg(saturation) FROM connection_stats
-- WHERE collected_at >= NOW() - INTERVAL '5 minutes';
