-- Enable UUID extension for secure, distributed IDs (Neon supports this out of the box)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Core Users Table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Brand Intelligence
-- Applying VADER here for brand perception will be very similar to how you 
-- analyzed market intelligence feeds for your financial dashboard.
CREATE TABLE brands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    vader_sentiment_score DECIMAL(5,4), -- Ranges from -1.0000 to 1.0000
    news_cache JSONB, -- Stores the raw snippets and URLs from the news aggregator API
    last_analyzed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Product Catalog (The "Health Tracking" Hub)
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brand_id UUID REFERENCES brands(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    barcode VARCHAR(100) UNIQUE,
    calories INTEGER,
    macros JSONB, -- Stores {"protein": X, "carbs": Y, "fats": Z} to avoid sparse columns
    data_source VARCHAR(50) DEFAULT 'open_food_facts', -- Tracks if 'open_food_facts' or 'gemini_estimated'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Smart Planning (Unstructured Input -> Structured Output)
CREATE TABLE grocery_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    raw_input TEXT NOT NULL, -- The original messy text or transcribed voice note
    parsed_items JSONB, -- Gemini's structured array of predicted items and desired quantities
    status VARCHAR(50) DEFAULT 'active', -- States: 'active', 'reconciled'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Active Pantry Inventory (The Reconciliation Output)
CREATE TABLE pantry_inventory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    product_id UUID REFERENCES products(id) ON DELETE RESTRICT,
    receipt_string VARCHAR(255), -- The cryptic abbreviation exactly as Gemini Vision extracted it
    quantity DECIMAL(10,2) DEFAULT 1.0,
    is_impulse_buy BOOLEAN DEFAULT FALSE,
    fuzzy_match_score INTEGER, -- Thefuzz ratio (0-100) linking it to a grocery_notes item
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance on background cron jobs and lookups
CREATE INDEX idx_products_brand ON products(brand_id);
CREATE INDEX idx_pantry_user ON pantry_inventory(user_id);
CREATE INDEX idx_brands_sentiment_date ON brands(last_analyzed_at);