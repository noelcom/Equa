-- Profil: kontots inställningar och gränser (GLOSSARY: Profil).
-- En profil per inloggad användare, skapas av backend vid första inloggning.
-- Gränserna ändras av Equas ägare direkt i Supabase (ADR 0006).

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  cv_quota_limit integer not null default 500 check (cv_quota_limit >= 0),
  default_retention_days integer not null default 7 check (default_retention_days > 0),
  max_retention_days integer not null default 90 check (max_retention_days > 0),
  max_file_size_mb integer not null default 25 check (max_file_size_mb > 0),
  created_at timestamptz not null default now(),
  check (default_retention_days <= max_retention_days)
);

alter table public.profiles enable row level security;

-- Radrättighet: en användare når bara sin egen rad.
create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using (id = (select auth.uid()));

-- ADR 0002: frontend pratar aldrig direkt med databasen. Ingen roll utanför
-- backend (service_role) får tabellrättigheter. RLS-policyn ovan är ett extra
-- lager om rättigheter någon gång ges av misstag.
revoke all on public.profiles from anon, authenticated;
