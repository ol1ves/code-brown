create table public.listings (
  item_id    text primary key,
  category   text not null,
  payload    jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index listings_category_idx   on public.listings (category);
create index listings_created_at_idx on public.listings (created_at desc);

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

create trigger listings_set_updated_at
before update on public.listings
for each row execute function public.set_updated_at();

alter table public.listings disable row level security;
