-- Phase 4: curated learning resources (seeded from ingestion/resources_seed.yaml).

create table public.learning_resources (
  id uuid primary key default gen_random_uuid(),
  skill_id text not null,           -- id in backend/app/skills/data/skills_taxonomy.json
  title text not null,
  url text not null check (url like 'https://%'),
  type text not null check (type in ('docs', 'course', 'video', 'book', 'practice')),
  level text not null check (level in ('beginner', 'intermediate', 'advanced')),
  est_hours numeric(6, 1) check (est_hours is null or est_hours > 0),
  free boolean not null default true,
  created_at timestamptz not null default now(),
  unique (skill_id, url)
);

create index learning_resources_skill_id_idx on public.learning_resources (skill_id);

-- Public reference data: anyone may read, only the backend (secret key) writes.
alter table public.learning_resources enable row level security;
create policy "learning_resources: public read" on public.learning_resources
  for select to anon, authenticated using (true);

grant select on public.learning_resources to anon, authenticated;
grant select, insert, update, delete on public.learning_resources to service_role;
