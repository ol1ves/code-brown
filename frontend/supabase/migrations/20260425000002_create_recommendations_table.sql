-- Create recommendations table for storing valued/ranked listings
CREATE TABLE IF NOT EXISTS recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id TEXT NOT NULL,
  query TEXT NOT NULL,
  scraped_at_unix BIGINT NOT NULL,
  
  -- Core ranking metrics (typed for sorting/filtering)
  edge_usd NUMERIC NOT NULL,           -- Expected dollar profit
  p_sell NUMERIC NOT NULL,             -- Probability the item sells (0-1)
  q50 NUMERIC NOT NULL,                -- Median expected sale price
  cost NUMERIC NOT NULL,               -- Total acquisition cost
  confidence TEXT NOT NULL,            -- "high" | "medium" | "low" | "insufficient"
  
  -- Full listing data
  live_listing JSONB NOT NULL,
  
  -- Opaque dicts for EV math and sell probability (additive-only)
  valuation JSONB NOT NULL DEFAULT '{}',
  sell_probability JSONB NOT NULL DEFAULT '{}',
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on item_id for lookups and deduplication
CREATE INDEX IF NOT EXISTS idx_recommendations_item_id ON recommendations(item_id);

-- Create index on edge_usd for sorting by profit
CREATE INDEX IF NOT EXISTS idx_recommendations_edge_usd ON recommendations(edge_usd DESC);

-- Create index on created_at for recency
CREATE INDEX IF NOT EXISTS idx_recommendations_created_at ON recommendations(created_at DESC);

-- Create composite index for the latest recommendation per item
CREATE INDEX IF NOT EXISTS idx_recommendations_item_created ON recommendations(item_id, created_at DESC);

-- Enable Row Level Security
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;

-- Create policy for service role access
CREATE POLICY "Service role has full access to recommendations" ON recommendations
  FOR ALL
  USING (true)
  WITH CHECK (true);
