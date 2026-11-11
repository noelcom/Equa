-- När ett CV senast tog ett steg framåt i en körning. Används för att ta om CV:n som
-- fastnat som queued/processing (t.ex. när servern startats om mitt i en körning).
alter table public.candidates
  add column claimed_at timestamptz;
