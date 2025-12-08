-- ===========================================
-- CoinBourg Database Initialization Script
-- ===========================================
-- PostgreSQL schema for the trading bot

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===========================================
-- Trades Table
-- ===========================================
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(64),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8),
    quantity DECIMAL(20, 8) NOT NULL,
    quote_quantity DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    pnl DECIMAL(20, 8),
    pnl_percent DECIMAL(10, 4),
    fees DECIMAL(20, 8),
    ai_confidence DECIMAL(5, 4),
    ai_reasoning TEXT,
    ai_sentiment VARCHAR(30),
    entry_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    exit_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_entry_time ON trades(entry_time);
CREATE INDEX idx_trades_side ON trades(side);

-- ===========================================
-- Positions Table
-- ===========================================
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL UNIQUE,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    current_price DECIMAL(20, 8),
    unrealized_pnl DECIMAL(20, 8),
    unrealized_pnl_percent DECIMAL(10, 4),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    trade_id UUID REFERENCES trades(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_positions_symbol ON positions(symbol);

-- ===========================================
-- Market Analysis Table
-- ===========================================
CREATE TABLE IF NOT EXISTS market_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    current_price DECIMAL(20, 8) NOT NULL,
    price_change_24h DECIMAL(10, 4),
    volume_24h DECIMAL(30, 8),
    sentiment VARCHAR(30),
    action VARCHAR(10),
    confidence DECIMAL(5, 4),
    entry_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    reasoning TEXT,
    indicators JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_analysis_symbol ON market_analysis(symbol);
CREATE INDEX idx_market_analysis_created_at ON market_analysis(created_at);

-- ===========================================
-- Performance Metrics Table
-- ===========================================
CREATE TABLE IF NOT EXISTS performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    date DATE NOT NULL UNIQUE,
    portfolio_value DECIMAL(20, 8),
    daily_pnl DECIMAL(20, 8),
    daily_pnl_percent DECIMAL(10, 4),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DECIMAL(5, 2),
    max_drawdown DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_performance_metrics_date ON performance_metrics(date);

-- ===========================================
-- Bot Configuration Table
-- ===========================================
CREATE TABLE IF NOT EXISTS bot_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Insert default configuration
INSERT INTO bot_config (key, value, description) VALUES
    ('risk_level', 'CONSERVATIVE', 'Current risk level setting'),
    ('max_position_size_percent', '5.0', 'Maximum position size as percentage of portfolio'),
    ('stop_loss_percent', '2.0', 'Default stop loss percentage'),
    ('take_profit_percent', '4.0', 'Default take profit percentage'),
    ('max_daily_trades', '10', 'Maximum number of trades per day'),
    ('trading_enabled', 'true', 'Whether automated trading is enabled')
ON CONFLICT (key) DO NOTHING;

-- ===========================================
-- Audit Log Table
-- ===========================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    details JSONB,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_action ON audit_log(action);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);

-- ===========================================
-- Functions and Triggers
-- ===========================================

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bot_config_updated_at
    BEFORE UPDATE ON bot_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===========================================
-- Views
-- ===========================================

-- Daily trading summary view
CREATE OR REPLACE VIEW daily_trading_summary AS
SELECT 
    DATE(entry_time) as trade_date,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE pnl > 0) as winning_trades,
    COUNT(*) FILTER (WHERE pnl < 0) as losing_trades,
    COALESCE(SUM(pnl), 0) as total_pnl,
    COALESCE(AVG(pnl_percent), 0) as avg_pnl_percent,
    ROUND(COUNT(*) FILTER (WHERE pnl > 0)::DECIMAL / NULLIF(COUNT(*), 0) * 100, 2) as win_rate
FROM trades
WHERE status = 'CLOSED'
GROUP BY DATE(entry_time)
ORDER BY trade_date DESC;

-- Symbol performance view
CREATE OR REPLACE VIEW symbol_performance AS
SELECT 
    symbol,
    COUNT(*) as total_trades,
    COUNT(*) FILTER (WHERE pnl > 0) as winning_trades,
    COALESCE(SUM(pnl), 0) as total_pnl,
    COALESCE(AVG(pnl_percent), 0) as avg_pnl_percent,
    COALESCE(AVG(ai_confidence), 0) as avg_ai_confidence
FROM trades
WHERE status = 'CLOSED'
GROUP BY symbol
ORDER BY total_pnl DESC;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO coinbourg;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO coinbourg;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO coinbourg;
