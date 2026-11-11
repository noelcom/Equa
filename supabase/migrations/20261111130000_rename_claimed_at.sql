-- claimed_at är en hjärtslagsstämpel (senaste framsteg), inte bara tidpunkten för anspråket.
alter table public.candidates
  rename column claimed_at to last_progress_at;
