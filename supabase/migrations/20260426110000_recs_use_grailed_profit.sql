-- Drop legacy index.
drop index if exists public.recommendations_edge_usd_idx;

-- Add new columns.
alter table public.recommendations
  add column expected_profit_grailed numeric,
  add column expected_profit_off_grailed numeric,
  add column buy_cost numeric,
  add column confidence_pct numeric;

-- Backfill from JSONB for existing rows when available.
update public.recommendations
set expected_profit_grailed = (valuation->'metrics'->>'expected_profit_grailed')::numeric,
    expected_profit_off_grailed = (valuation->'metrics'->>'expected_profit_off_grailed')::numeric,
    buy_cost = (valuation->>'buy_cost')::numeric,
    confidence_pct = (valuation->'metrics'->>'confidence_percentage')::numeric;

-- Enforce not-null moving forward.
alter table public.recommendations
  alter column expected_profit_grailed set not null,
  alter column expected_profit_off_grailed set not null,
  alter column buy_cost set not null,
  alter column confidence_pct set not null;

-- Drop legacy columns.
alter table public.recommendations
  drop column edge_usd,
  drop column cost,
  drop column confidence;

-- New index for ranking.
create index recommendations_expected_profit_grailed_idx
  on public.recommendations (expected_profit_grailed desc);

-- Replace RPC: latest unique listing, ordered by expected_profit_grailed.
create or replace function public.list_latest_recommendations(p_limit int)
returns setof public.recommendations
language sql stable as $$
  with latest as (
    select distinct on (
      live_listing->'seller'->>'seller_name',
      live_listing->>'name',
      live_listing->>'size',
      live_listing->'price'->>'listing_price_usd'
    ) *
    from public.recommendations
    order by
      live_listing->'seller'->>'seller_name',
      live_listing->>'name',
      live_listing->>'size',
      live_listing->'price'->>'listing_price_usd',
      scraped_at_unix desc,
      expected_profit_grailed desc
  )
  select * from latest
  order by expected_profit_grailed desc
  limit p_limit;
$$;
