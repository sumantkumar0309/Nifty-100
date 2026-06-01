CREATE TABLE IF NOT EXISTS dim_sector (
    sector_id INT PRIMARY KEY,
    sector_name VARCHAR(100) NOT NULL UNIQUE,
    sector_code VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS dim_company (
    symbol VARCHAR(20) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    sector_id INT REFERENCES dim_sector(sector_id),
    sector_name VARCHAR(100),
    company_logo TEXT,
    website TEXT,
    nse_url TEXT,
    bse_url TEXT,
    face_value NUMERIC(18,4),
    book_value NUMERIC(18,4),
    about_company TEXT
);

CREATE TABLE IF NOT EXISTS dim_year (
    year_id INT PRIMARY KEY,
    year_label VARCHAR(30) NOT NULL UNIQUE,
    fiscal_year INT,
    quarter VARCHAR(10),
    is_ttm BOOLEAN DEFAULT FALSE,
    is_half_year BOOLEAN DEFAULT FALSE,
    sort_order INT
);

CREATE TABLE IF NOT EXISTS dim_health_label (
    label_id INT PRIMARY KEY,
    label_name VARCHAR(20) NOT NULL UNIQUE,
    min_score NUMERIC(5,2) NOT NULL,
    max_score NUMERIC(5,2) NOT NULL,
    color_hex VARCHAR(7) NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_profit_loss (
    symbol VARCHAR(20) NOT NULL REFERENCES dim_company(symbol),
    year_id INT NOT NULL REFERENCES dim_year(year_id),
    sales NUMERIC(20,4),
    expenses NUMERIC(20,4),
    operating_profit NUMERIC(20,4),
    opm_pct NUMERIC(10,4),
    other_income NUMERIC(20,4),
    interest NUMERIC(20,4),
    depreciation NUMERIC(20,4),
    profit_before_tax NUMERIC(20,4),
    tax_pct NUMERIC(10,4),
    net_profit NUMERIC(20,4),
    eps NUMERIC(20,4),
    dividend_payout_pct NUMERIC(10,4),
    net_profit_margin_pct NUMERIC(10,4),
    expense_ratio_pct NUMERIC(10,4),
    interest_coverage NUMERIC(20,6),
    asset_turnover NUMERIC(20,6),
    return_on_assets NUMERIC(10,4),
    PRIMARY KEY (symbol, year_id)
);

CREATE TABLE IF NOT EXISTS fact_balance_sheet (
    symbol VARCHAR(20) NOT NULL REFERENCES dim_company(symbol),
    year_id INT NOT NULL REFERENCES dim_year(year_id),
    equity_capital NUMERIC(20,4),
    reserves NUMERIC(20,4),
    borrowings NUMERIC(20,4),
    other_liabilities NUMERIC(20,4),
    total_liabilities NUMERIC(20,4),
    fixed_assets NUMERIC(20,4),
    cwip NUMERIC(20,4),
    investments NUMERIC(20,4),
    other_assets NUMERIC(20,4),
    total_assets NUMERIC(20,4),
    debt_to_equity NUMERIC(20,6),
    equity_ratio NUMERIC(20,6),
    shares_outstanding NUMERIC(20,4),
    book_value_per_share NUMERIC(20,6),
    PRIMARY KEY (symbol, year_id)
);

CREATE TABLE IF NOT EXISTS fact_cash_flow (
    symbol VARCHAR(20) NOT NULL REFERENCES dim_company(symbol),
    year_id INT NOT NULL REFERENCES dim_year(year_id),
    operating_activity NUMERIC(20,4),
    investing_activity NUMERIC(20,4),
    financing_activity NUMERIC(20,4),
    net_cash_flow NUMERIC(20,4),
    free_cash_flow NUMERIC(20,4),
    cash_conversion_ratio NUMERIC(20,6),
    PRIMARY KEY (symbol, year_id)
);

CREATE TABLE IF NOT EXISTS fact_analysis (
    symbol VARCHAR(20) NOT NULL REFERENCES dim_company(symbol),
    period_label VARCHAR(10) NOT NULL,
    compounded_sales_growth_pct NUMERIC(10,4),
    compounded_profit_growth_pct NUMERIC(10,4),
    stock_price_cagr_pct NUMERIC(10,4),
    roe_pct NUMERIC(10,4),
    PRIMARY KEY (symbol, period_label)
);

CREATE TABLE IF NOT EXISTS fact_ml_scores (
    symbol VARCHAR(20) NOT NULL REFERENCES dim_company(symbol),
    computed_at TIMESTAMPTZ NOT NULL,
    overall_score NUMERIC(10,4),
    profitability_score NUMERIC(10,4),
    growth_score NUMERIC(10,4),
    leverage_score NUMERIC(10,4),
    cashflow_score NUMERIC(10,4),
    dividend_score NUMERIC(10,4),
    trend_score NUMERIC(10,4),
    health_label VARCHAR(20),
    PRIMARY KEY (symbol, computed_at)
);

CREATE TABLE IF NOT EXISTS fact_pros_cons (
    insight_id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL REFERENCES dim_company(symbol),
    is_pro BOOLEAN NOT NULL,
    category VARCHAR(100),
    text TEXT NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    confidence NUMERIC(6,4),
    generated_at TIMESTAMPTZ,
    UNIQUE (symbol, is_pro, text)
);

CREATE INDEX IF NOT EXISTS idx_dim_company_sector_id ON dim_company(sector_id);
CREATE INDEX IF NOT EXISTS idx_dim_year_sort_order ON dim_year(sort_order);
CREATE INDEX IF NOT EXISTS idx_fact_profit_loss_year ON fact_profit_loss(year_id);
CREATE INDEX IF NOT EXISTS idx_fact_balance_sheet_year ON fact_balance_sheet(year_id);
CREATE INDEX IF NOT EXISTS idx_fact_cash_flow_year ON fact_cash_flow(year_id);
CREATE INDEX IF NOT EXISTS idx_fact_ml_scores_computed_at ON fact_ml_scores(computed_at);
