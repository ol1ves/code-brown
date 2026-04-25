-- Create RPC function to get latest recommendation per item_id
-- This is the cheap read path used by GET /recommendations
CREATE OR REPLACE FUNCTION list_latest_recommendations(result_limit INTEGER DEFAULT 50)
RETURNS TABLE (
  id UUID,
  item_id TEXT,
  query TEXT,
  scraped_at_unix BIGINT,
  edge_usd NUMERIC,
  p_sell NUMERIC,
  q50 NUMERIC,
  cost NUMERIC,
  confidence TEXT,
  live_listing JSONB,
  valuation JSONB,
  sell_probability JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
  SELECT DISTINCT ON (r.item_id)
    r.id,
    r.item_id,
    r.query,
    r.scraped_at_unix,
    r.edge_usd,
    r.p_sell,
    r.q50,
    r.cost,
    r.confidence,
    r.live_listing,
    r.valuation,
    r.sell_probability,
    r.created_at,
    r.updated_at
  FROM recommendations r
  ORDER BY r.item_id, r.created_at DESC
  LIMIT result_limit;
$$;

-- Create a version that also sorts by edge_usd (most profitable first)
CREATE OR REPLACE FUNCTION list_latest_recommendations_by_profit(result_limit INTEGER DEFAULT 50)
RETURNS TABLE (
  id UUID,
  item_id TEXT,
  query TEXT,
  scraped_at_unix BIGINT,
  edge_usd NUMERIC,
  p_sell NUMERIC,
  q50 NUMERIC,
  cost NUMERIC,
  confidence TEXT,
  live_listing JSONB,
  valuation JSONB,
  sell_probability JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
  WITH latest AS (
    SELECT DISTINCT ON (r.item_id)
      r.id,
      r.item_id,
      r.query,
      r.scraped_at_unix,
      r.edge_usd,
      r.p_sell,
      r.q50,
      r.cost,
      r.confidence,
      r.live_listing,
      r.valuation,
      r.sell_probability,
      r.created_at,
      r.updated_at
    FROM recommendations r
    ORDER BY r.item_id, r.created_at DESC
  )
  SELECT * FROM latest
  ORDER BY edge_usd DESC
  LIMIT result_limit;
$$;
