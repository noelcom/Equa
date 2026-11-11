-- Användningslogg: permanent, anonymiserad rad per körning (GLOSSARY: Användningslogg).
-- Underlag för fakturering och för månadskvoten, så den överlever att analysen raderas.
-- Ingen kandidatdata och ingen främmande nyckel: raden ska finnas kvar efter radering
-- av analys, kandidater och konto (customer_id är bara ett id, inga personuppgifter).

create table public.usage_logs (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null,
  created_at timestamptz not null default now(),
  -- Antal lyckade CV:n i körningen. Det är bara de som räknas mot kvoten.
  cv_count integer not null check (cv_count >= 0),
  input_tokens integer not null check (input_tokens >= 0),
  output_tokens integer not null check (output_tokens >= 0)
);

create index usage_logs_customer_month_idx on public.usage_logs (customer_id, created_at);

alter table public.usage_logs enable row level security;
revoke all on public.usage_logs from anon, authenticated;
grant select, insert, delete on public.usage_logs to service_role;
