-- Create listings table for storing scraped Grailed listings
-- Schema matches store.py ListingStore

create table if not exists public.listings (
  item_id    text primary key,
  category   text not null,
  payload    jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Indexes for common queries
create index if not exists listings_category_idx on public.listings (category);
create index if not exists listings_created_at_idx on public.listings (created_at desc);

-- Auto-update updated_at timestamp
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists listings_set_updated_at on public.listings;
create trigger listings_set_updated_at
before update on public.listings
for each row execute function public.set_updated_at();

-- Disable RLS for now (internal service access)
alter table public.listings disable row level security;
