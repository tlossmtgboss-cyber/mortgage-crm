-- ============================================================================
-- Rate Watch System — Schema Migration
-- Author: Architect + Data Engineer (Perennia AI dev team)
-- Date:   2026-05-17
--
-- Tables created:
--   rate_observations        — every fetched rate from every source (time-series)
--   rate_margins             — Perennia margin per product, with audit history
--   borrower_target_rates    — per-borrower target rate (drives match engine)
--   refi_opportunities       — emitted when a borrower's target is hit
--   rate_watch_run_log       — every ingestion run, for ops/debugging
--
-- Design notes:
--   - rate_observations is the source-of-truth time-series. Append-only.
--     Dedup key: (source, product, observed_at) UNIQUE.
--   - rate_margins is versioned (no UPDATE; new row supersedes). Audit-friendly.
--   - refi_opportunities is the *event log* of detected matches. The Aria/CRM
--     event bus consumes from here. NEVER updated; superseded by a new row.
--   - All money columns are NUMERIC, never FLOAT (QA + Security veto).
--   - All rates stored as NUMERIC(7,4) — supports 0.0000 to 999.9999.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. rate_watch_run_log
--    Every poll attempt. Used for ops dashboards and silent-failure alerting.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_watch_run_log (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,                  -- 'mnd_html' | 'optimal_blue' | 'fred'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL,                  -- 'running' | 'success' | 'soft_fail' | 'hard_fail'
    rows_observed   INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    error_kind      TEXT,                           -- 'http_error' | 'parse_error' | 'schema_drift' | 'rate_limited' | 'timeout'
    fetch_duration_ms INTEGER,
    upstream_etag   TEXT,                           -- if source returns one, store for conditional GET
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_run_log_source_started
    ON rate_watch_run_log (source, started_at DESC);

CREATE INDEX idx_run_log_status_started
    ON rate_watch_run_log (status, started_at DESC)
    WHERE status IN ('hard_fail', 'soft_fail');

COMMENT ON TABLE rate_watch_run_log IS
    'Every ingestion run. Drives "no successful fetch in N minutes" alerting.';

-- ----------------------------------------------------------------------------
-- 2. rate_observations
--    The time-series of market rates. Append-only. Source of truth.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_observations (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,                  -- 'mnd_html' | 'optimal_blue' | 'fred'
    product         TEXT NOT NULL,                  -- '30_fixed' | '15_fixed' | '30_jumbo' | '7_6_sofr_arm' | '30_fha' | '30_va'
    rate            NUMERIC(7,4) NOT NULL,          -- e.g. 6.6500
    points          NUMERIC(5,3) NOT NULL DEFAULT 0.000,
    change_pct      NUMERIC(7,4),                   -- day-over-day delta if upstream provides
    observed_at     TIMESTAMPTZ NOT NULL,           -- when the upstream says this rate was effective
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fetch_run_id    BIGINT NOT NULL REFERENCES rate_watch_run_log(id),
    raw_payload     JSONB,                          -- whatever the source returned; for forensics
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT rate_observations_dedup UNIQUE (source, product, observed_at),
    CONSTRAINT rate_observations_rate_sane CHECK (rate >= 0 AND rate <= 30),
    CONSTRAINT rate_observations_product_valid CHECK (
        product IN ('30_fixed','15_fixed','30_jumbo','7_6_sofr_arm','30_fha','30_va','20_fixed','10_fixed')
    )
);

CREATE INDEX idx_obs_product_observed
    ON rate_observations (product, observed_at DESC);

CREATE INDEX idx_obs_source_product_observed
    ON rate_observations (source, product, observed_at DESC);

-- "latest per product" partial index for hot queries
CREATE INDEX idx_obs_recent
    ON rate_observations (product, observed_at DESC)
    WHERE observed_at > NOW() - INTERVAL '7 days';

COMMENT ON TABLE rate_observations IS
    'Time-series of market rate observations. Append-only. Dedup: (source, product, observed_at).';

-- ----------------------------------------------------------------------------
-- 3. rate_margins
--    Perennia's margin per product. Versioned — new row supersedes prior.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_margins (
    id              BIGSERIAL PRIMARY KEY,
    product         TEXT NOT NULL,
    margin_bps      INTEGER NOT NULL,               -- basis points. 25 = 0.25%
    scope           TEXT NOT NULL DEFAULT 'global', -- 'global' | 'lo_override'
    loan_officer_id UUID,                           -- non-null only when scope='lo_override'
    effective_from  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_to    TIMESTAMPTZ,                    -- null = currently active
    created_by      UUID NOT NULL,                  -- user who set it
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT rate_margins_bps_sane CHECK (margin_bps BETWEEN -500 AND 500),
    CONSTRAINT rate_margins_lo_scope CHECK (
        (scope = 'lo_override' AND loan_officer_id IS NOT NULL)
        OR (scope = 'global'   AND loan_officer_id IS NULL)
    ),
    CONSTRAINT rate_margins_product_valid CHECK (
        product IN ('30_fixed','15_fixed','30_jumbo','7_6_sofr_arm','30_fha','30_va','20_fixed','10_fixed')
    )
);

-- One active global margin per product
CREATE UNIQUE INDEX uq_margins_active_global
    ON rate_margins (product)
    WHERE scope = 'global' AND effective_to IS NULL;

-- One active LO override per (LO, product)
CREATE UNIQUE INDEX uq_margins_active_lo
    ON rate_margins (loan_officer_id, product)
    WHERE scope = 'lo_override' AND effective_to IS NULL;

COMMENT ON TABLE rate_margins IS
    'Perennia rate = market_rate - margin_bps/10000. Versioned via effective_to.';

-- Seed default 25 bps (0.25%) margin for the products from the screenshot
INSERT INTO rate_margins (product, margin_bps, scope, created_by, note)
SELECT p, 25, 'global', '00000000-0000-0000-0000-000000000000'::uuid, 'Initial seed'
FROM UNNEST(ARRAY['30_fixed','15_fixed','30_jumbo','7_6_sofr_arm','30_fha','30_va']) AS p
ON CONFLICT DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. borrower_target_rates
--    Per-borrower target. Drives the match engine.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS borrower_target_rates (
    id                  BIGSERIAL PRIMARY KEY,
    borrower_id         UUID NOT NULL,              -- FK to your borrowers table
    loan_id             INTEGER NOT NULL REFERENCES loans(id),  -- FK to your loans table (the current loan)
    product             TEXT NOT NULL,              -- the product they'd refi INTO (often same as current)
    target_rate         NUMERIC(7,4) NOT NULL,      -- the rate that triggers outreach
    min_monthly_savings NUMERIC(10,2),              -- floor: don't trigger if savings below this
    min_break_even_months INTEGER,                  -- floor: don't trigger if break-even worse than this
    cooldown_days       INTEGER NOT NULL DEFAULT 30,-- don't re-trigger within this window
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source              TEXT NOT NULL,              -- 'borrower_set' | 'lo_set' | 'auto_inferred'

    CONSTRAINT btr_target_sane CHECK (target_rate > 0 AND target_rate < 30),
    CONSTRAINT btr_one_active_per_loan UNIQUE (loan_id, active) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX idx_btr_active_product
    ON borrower_target_rates (product, target_rate)
    WHERE active = TRUE;

CREATE INDEX idx_btr_borrower
    ON borrower_target_rates (borrower_id);

COMMENT ON TABLE borrower_target_rates IS
    'Per-loan refi target. Match engine compares perennia_rate(product) <= target_rate.';

-- ----------------------------------------------------------------------------
-- 5. refi_opportunities
--    Event log of detected matches. Append-only. Drives outreach.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refi_opportunities (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_id                 UUID NOT NULL,
    borrower_id             UUID NOT NULL,
    loan_officer_id         UUID NOT NULL,
    product                 TEXT NOT NULL,
    target_rate             NUMERIC(7,4) NOT NULL,
    market_rate             NUMERIC(7,4) NOT NULL,
    perennia_rate           NUMERIC(7,4) NOT NULL,
    margin_bps_at_detection INTEGER NOT NULL,
    rate_observation_id     BIGINT NOT NULL REFERENCES rate_observations(id),

    -- Savings math snapshot — captured at detection time so we can replay the decision
    current_balance         NUMERIC(12,2) NOT NULL,
    current_rate            NUMERIC(7,4) NOT NULL,
    current_payment         NUMERIC(10,2) NOT NULL,
    projected_payment       NUMERIC(10,2) NOT NULL,
    monthly_savings         NUMERIC(10,2) NOT NULL,
    estimated_break_even_months INTEGER,

    status                  TEXT NOT NULL DEFAULT 'detected',
    -- 'detected' → 'outreach_sent' → 'borrower_responded' → 'meeting_booked' → 'closed_won' | 'closed_lost' | 'expired'

    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at              TIMESTAMPTZ NOT NULL,
    outreach_dispatched_at  TIMESTAMPTZ,
    meeting_booked_at       TIMESTAMPTZ,
    calendar_event_id       UUID,                   -- FK to your Smart Calendar event

    -- TCPA / compliance receipts
    tcpa_consent_verified   BOOLEAN NOT NULL,
    tcpa_consent_id         UUID,
    quiet_hours_check_passed BOOLEAN NOT NULL,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT refi_status_valid CHECK (
        status IN ('detected','outreach_sent','borrower_responded','meeting_booked','closed_won','closed_lost','expired')
    )
);

CREATE INDEX idx_refi_loan_detected
    ON refi_opportunities (loan_id, detected_at DESC);

CREATE INDEX idx_refi_status
    ON refi_opportunities (status, detected_at DESC)
    WHERE status NOT IN ('closed_won','closed_lost','expired');

CREATE INDEX idx_refi_lo_dashboard
    ON refi_opportunities (loan_officer_id, status, detected_at DESC);

COMMENT ON TABLE refi_opportunities IS
    'Event log of refi triggers. Status transitions are tracked. Snapshot fields captured at detection.';

-- ----------------------------------------------------------------------------
-- 6. Helper view: current_rates
--    Latest observation per product, joined with active global margin.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW current_rates AS
WITH latest_obs AS (
    SELECT DISTINCT ON (product)
        product,
        rate AS market_rate,
        points,
        observed_at,
        source,
        id AS observation_id
    FROM rate_observations
    WHERE observed_at > NOW() - INTERVAL '7 days'
    ORDER BY product, observed_at DESC
),
active_margin AS (
    SELECT product, margin_bps
    FROM rate_margins
    WHERE scope = 'global' AND effective_to IS NULL
)
SELECT
    lo.product,
    lo.market_rate,
    lo.points,
    lo.observed_at,
    lo.source,
    lo.observation_id,
    am.margin_bps,
    (lo.market_rate - am.margin_bps::NUMERIC / 100.0) AS perennia_rate
FROM latest_obs lo
LEFT JOIN active_margin am ON am.product = lo.product;

COMMENT ON VIEW current_rates IS
    'One row per product: latest market rate + active margin + computed Perennia rate.';

COMMIT;

-- ============================================================================
-- ROLLBACK (run only if you need to fully undo)
-- ============================================================================
-- BEGIN;
--   DROP VIEW IF EXISTS current_rates;
--   DROP TABLE IF EXISTS refi_opportunities;
--   DROP TABLE IF EXISTS borrower_target_rates;
--   DROP TABLE IF EXISTS rate_margins;
--   DROP TABLE IF EXISTS rate_observations;
--   DROP TABLE IF EXISTS rate_watch_run_log;
-- COMMIT;
