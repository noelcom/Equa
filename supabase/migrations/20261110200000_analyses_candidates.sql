-- Analys, kandidat och lagring av originalfiler (GLOSSARY: Analys, Kandidat, Originalfil).
-- Som profiles: ingen roll utanför backend (service_role) når tabellerna (ADR 0002).

create table public.analysis_batches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null check (length(trim(title)) > 0),
  job_ad text not null check (length(trim(job_ad)) > 0),
  -- Raderingsdatum: när analysen och dess originalfiler raderas (ADR 0004).
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index analysis_batches_user_id_idx on public.analysis_batches (user_id, created_at desc);
create index analysis_batches_expires_at_idx on public.analysis_batches (expires_at);

create table public.candidates (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analysis_batches (id) on delete cascade,
  -- Löpnummer i analysen. Visas som "Kandidat #N" (anonym alias).
  number integer not null check (number > 0),
  -- Sökväg till originalfilen i bucketen "originals". Aldrig originalfilnamnet.
  original_path text not null,
  created_at timestamptz not null default now(),
  unique (analysis_id, number)
);

alter table public.analysis_batches enable row level security;
alter table public.candidates enable row level security;

create policy "analysis_batches_select_own"
  on public.analysis_batches for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy "candidates_select_own"
  on public.candidates for select
  to authenticated
  using (
    exists (
      select 1 from public.analysis_batches a
      where a.id = candidates.analysis_id and a.user_id = (select auth.uid())
    )
  );

revoke all on public.analysis_batches, public.candidates from anon, authenticated;
grant select, insert, update, delete on public.analysis_batches, public.candidates to service_role;

-- Privat bucket för originalfiler. Supabase Storage krypterar vilande data.
-- Ingen storage-policy skapas, så bara service_role (backend) når filerna.
insert into storage.buckets (id, name, public)
values ('originals', 'originals', false)
on conflict (id) do nothing;
