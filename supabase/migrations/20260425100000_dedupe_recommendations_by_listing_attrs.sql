-- Replace list_latest_recommendations to dedupe near-identical seller relistings.
-- Same seller posting "guidi 788z size 37" three times under different item_ids
-- should collapse to one row at read time. Group key:
--   (seller_name, name, size, listing_price_usd)
-- Within a group, keep the freshest scrape (then highest edge as tie-break),
-- then re-rank globally by edge_usd desc.
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
      edge_usd desc
  )
  select * from latest
  order by edge_usd desc
  limit p_limit;
$$;
