create table public.recommendations (
  id              uuid primary key default gen_random_uuid(),
  item_id         text not null,
  scraped_at_unix bigint not null,
  query           text not null,
  params          jsonb not null,
  edge_usd        numeric not null,
  p_sell          numeric not null,
  q50             numeric not null,
  cost            numeric not null,
  confidence      text not null,
  valuation       jsonb not null,
  sell_probability jsonb not null,
  live_listing    jsonb not null,
  created_at      timestamptz not null default now()
);

create index recommendations_item_id_scraped_at_idx
  on public.recommendations (item_id, scraped_at_unix desc);
create index recommendations_edge_usd_idx
  on public.recommendations (edge_usd desc);
create index recommendations_created_at_idx
  on public.recommendations (created_at desc);

alter table public.recommendations disable row level security;

create or replace function public.list_latest_recommendations(p_limit int)
returns setof public.recommendations
language sql stable as $$
  with latest as (
    select distinct on (item_id) *
    from public.recommendations
    order by item_id, scraped_at_unix desc, edge_usd desc
  )
  select * from latest
  order by edge_usd desc
  limit p_limit;
$$;
