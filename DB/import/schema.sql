-- =============================================================================
-- PotSystem PostgreSQL Schema
-- Database: potsystem
-- =============================================================================
-- Conventions:
--   - All identifiers lowercase with underscores
--   - Daynums stored as INTEGER (system-internal trading day counter)
--   - Dates stored as DATE
--   - European-format numbers (comma decimal, semicolon sep) converted on import
--   - Tickers follow Yahoo format; ^ prefix = index/indicator
--   - Timestamps for fetched_at stored as TIMESTAMPTZ
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. CAL — Trading day calendar
--    Maps daynum (integer counter) to actual calendar date
--    Foundation for all time-based joins
-- -----------------------------------------------------------------------------
CREATE TABLE cal (
    daynum      INTEGER     NOT NULL,
    date        DATE        NOT NULL,
    CONSTRAINT pk_cal PRIMARY KEY (daynum),
    CONSTRAINT uq_cal_date UNIQUE (date)
);

-- -----------------------------------------------------------------------------
-- 2. STOCKS — Master list of all tickers
--    One row per ticker. Source: Stamdata.csv
--    Tickers with ^ prefix are indices/market indicators
-- -----------------------------------------------------------------------------
CREATE TABLE stocks (
    ticker          VARCHAR(20)     NOT NULL,
    google_id       VARCHAR(100),
    name            VARCHAR(200),
    sector          VARCHAR(100),
    homeland        VARCHAR(50),
    gics            VARCHAR(100),
    link_summary    VARCHAR(500),
    link_yahoo      VARCHAR(500),
    company_website VARCHAR(500),
    stam_note       VARCHAR(500),
    sm_ejet         BOOLEAN,
    fk_analyse      BOOLEAN,
    fkplus          NUMERIC(6,4),
    fkyr            INTEGER,
    oprettet        DATE,
    valuta          VARCHAR(10),
    nper_adr        NUMERIC(10,4),
    sgrp1           VARCHAR(50),
    protected       BOOLEAN,
    sector2         VARCHAR(100),
    check_flag      VARCHAR(50),
    exchange        VARCHAR(20),
    zone            VARCHAR(20),
    core_index      VARCHAR(20),
    yahoo2          VARCHAR(20),
    CONSTRAINT pk_stocks PRIMARY KEY (ticker)
);

-- -----------------------------------------------------------------------------
-- 3. PRICES — End-of-day close prices
--    Source: PotDatC.csv (wide format → unpivoted on import)
--    One row per ticker per trading day
--    This is the central time-series table
-- -----------------------------------------------------------------------------
CREATE TABLE prices (
    ticker      VARCHAR(20)     NOT NULL,
    daynum      INTEGER         NOT NULL,
    close       NUMERIC(18,6),
    CONSTRAINT pk_prices PRIMARY KEY (ticker, daynum),
    CONSTRAINT fk_prices_ticker FOREIGN KEY (ticker) REFERENCES stocks(ticker),
    CONSTRAINT fk_prices_daynum FOREIGN KEY (daynum) REFERENCES cal(daynum)
);

CREATE INDEX ix_prices_daynum ON prices(daynum);
CREATE INDEX ix_prices_ticker ON prices(ticker);

-- -----------------------------------------------------------------------------
-- 4. YFINANCE — Fundamental data from Yahoo Finance
--    Source: Stockdata2_stacked.csv (already long format)
--    One row per ticker per fetch timestamp
-- -----------------------------------------------------------------------------
CREATE TABLE yfinance (
    ticker                  VARCHAR(20)     NOT NULL,
    fetched_date            TIMESTAMPTZ     NOT NULL,
    previous_close          NUMERIC(18,6),
    current_price           NUMERIC(18,6),
    dividend_rate           NUMERIC(10,6),
    dividend_yield_pct      NUMERIC(10,6),
    ex_div_date             DATE,
    pe_ttm                  NUMERIC(12,4),
    pe_fwd                  NUMERIC(12,4),
    ps_ttm                  NUMERIC(12,4),
    profit_margin           NUMERIC(10,6),
    float_shares            NUMERIC(20,0),
    book_value              NUMERIC(12,4),
    pb                      NUMERIC(12,4),
    eps_ttm                 NUMERIC(12,4),
    eps_fwd                 NUMERIC(12,4),
    dividend_last           NUMERIC(10,6),
    date_dividend_last      DATE,
    target_high_price       NUMERIC(12,4),
    target_low_price        NUMERIC(12,4),
    target_mean_price       NUMERIC(12,4),
    target_median_price     NUMERIC(12,4),
    recommendation_mean     NUMERIC(6,4),
    recommendation_key      VARCHAR(20),
    number_of_analysts      INTEGER,
    revenue_total           NUMERIC(20,0),
    revenue_per_share       NUMERIC(12,4),
    free_cash_flow          NUMERIC(20,0),
    earnings_growth         NUMERIC(10,6),
    revenue_growth          NUMERIC(10,6),
    gross_margin            NUMERIC(10,6),
    ebitda_margin           NUMERIC(10,6),
    operating_margin        NUMERIC(10,6),
    trailing_peg            NUMERIC(12,4),
    full_time_employees     INTEGER,
    CONSTRAINT pk_yfinance PRIMARY KEY (ticker, fetched_date),
    CONSTRAINT fk_yfinance_ticker FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);

CREATE INDEX ix_yfinance_ticker ON yfinance(ticker);
CREATE INDEX ix_yfinance_fetched ON yfinance(fetched_date);

-- -----------------------------------------------------------------------------
-- 5. LONGI — Computed indicators (long/narrow format)
--    Sources: longi_*.csv + future_gain20d.csv + future_gain50d.csv
--    All wide-format files unpivoted and stacked into one table
--    indicator column holds the filename stem (e.g. 'ma10', 'rsi', 'beta3m')
--    Adding/removing indicators requires no schema change
-- -----------------------------------------------------------------------------
CREATE TABLE longi (
    ticker      VARCHAR(20)     NOT NULL,
    daynum      INTEGER         NOT NULL,
    indicator   VARCHAR(50)     NOT NULL,
    value       NUMERIC(18,6),
    CONSTRAINT pk_longi PRIMARY KEY (ticker, daynum, indicator),
    CONSTRAINT fk_longi_ticker FOREIGN KEY (ticker) REFERENCES stocks(ticker),
    CONSTRAINT fk_longi_daynum FOREIGN KEY (daynum) REFERENCES cal(daynum)
);

CREATE INDEX ix_longi_ticker    ON longi(ticker);
CREATE INDEX ix_longi_daynum    ON longi(daynum);
CREATE INDEX ix_longi_indicator ON longi(indicator);

-- -----------------------------------------------------------------------------
-- 6. AUX_DECILES — Decile boundaries for indicators
--    Source: aux_deciles.csv (already long format)
--    Used for ranking/classification of indicator values
-- -----------------------------------------------------------------------------
CREATE TABLE aux_deciles (
    indicator   VARCHAR(50)     NOT NULL,
    decile      INTEGER         NOT NULL,
    upper_limit NUMERIC(18,6),
    lower_limit NUMERIC(18,6),
    CONSTRAINT pk_aux_deciles PRIMARY KEY (indicator, decile)
);

-- -----------------------------------------------------------------------------
-- 7. AUX_WIN_LOSS — Prediction probabilities per ticker per day
--    Source: aux_win-loss.csv (already long format)
--    Holds ML prediction labels and win/loss probabilities
--    for 20-day and 50-day forward horizons
-- -----------------------------------------------------------------------------
CREATE TABLE aux_win_loss (
    daynum          INTEGER         NOT NULL,
    ticker          VARCHAR(20)     NOT NULL,
    pred_label_20d  VARCHAR(10),
    p_win_20d       NUMERIC(18,15),
    p_loss_20d      NUMERIC(18,15),
    pred_label_50d  VARCHAR(10),
    p_win_50d       NUMERIC(18,15),
    p_loss_50d      NUMERIC(18,15),
    CONSTRAINT pk_aux_win_loss PRIMARY KEY (daynum, ticker),
    CONSTRAINT fk_aux_win_loss_ticker FOREIGN KEY (ticker) REFERENCES stocks(ticker),
    CONSTRAINT fk_aux_win_loss_daynum FOREIGN KEY (daynum) REFERENCES cal(daynum)
);

CREATE INDEX ix_aux_win_loss_ticker ON aux_win_loss(ticker);

-- -----------------------------------------------------------------------------
-- 8. LONGI_GRP — Aggregated indicators by group label
--    Source: Longi/output_grp/*.csv
--    Same structure as longi but first column is a group label
--    (e.g. sector name, GICS code, country) instead of ticker
--    indicator column holds the file stem (e.g. 'GICS_1yr', 'Sector2_3m')
-- -----------------------------------------------------------------------------
CREATE TABLE longi_grp (
    group_label VARCHAR(100)    NOT NULL,
    daynum      INTEGER         NOT NULL,
    indicator   VARCHAR(50)     NOT NULL,
    value       NUMERIC(18,6),
    CONSTRAINT pk_longi_grp PRIMARY KEY (group_label, daynum, indicator),
    CONSTRAINT fk_longi_grp_daynum FOREIGN KEY (daynum) REFERENCES cal(daynum)
);

CREATE INDEX ix_longi_grp_label     ON longi_grp(group_label);
CREATE INDEX ix_longi_grp_daynum    ON longi_grp(daynum);
CREATE INDEX ix_longi_grp_indicator ON longi_grp(indicator);

