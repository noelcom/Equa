-- Pipelinens tillstånd och bedömningsresultat per kandidat (GLOSSARY: Bedömning, Poäng).
--
-- Medvetet ingen kolumn för tvättad text: den hålls bara i minnet under körningen
-- och sparas aldrig (ADR 0004).

alter table public.candidates
  -- uploaded: uppladdad men inte körd. queued/processing: under körning.
  -- done: bedömd. failed: "Kunde inte analyseras" (eget tillstånd, aldrig poäng 0).
  add column status text not null default 'uploaded'
    check (status in ('uploaded', 'queued', 'processing', 'done', 'failed')),
  -- Aktuellt pipelinesteg, för realtidsprogress.
  add column step text
    check (step in ('pre_wash', 'ai_wash', 'safety_check', 'assessment')),
  add column score integer check (score between 0 and 100),
  add column years_experience integer check (years_experience >= 0),
  add column education_match text,
  add column concrete_results text,
  add column key_skills text[],
  add column missing_requirements text,
  add column rationale text,
  -- Kort, standardiserad orsak. Innehåller aldrig CV-text.
  add column failure_reason text,
  add constraint candidates_failed_has_no_score check (status <> 'failed' or score is null),
  add constraint candidates_done_has_score check (status <> 'done' or score is not null);
