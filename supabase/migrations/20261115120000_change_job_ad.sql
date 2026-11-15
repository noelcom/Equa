-- Byt arbetsannons och köa om alla CV:n i en och samma transaktion (#30, GLOSSARY: Arbetsannons).
--
-- Två steg i backend lät en samtidig körning ta CV:n med den gamla annonsen mellan bytet
-- och anspråket. Här låser funktionen analysens CV:n först, så en körning som anspråkar
-- samma rader väntar tills bytet är klart och sedan inte längre hittar dem som uppladdade.
--
-- Annonsen byts bara om den är oförändrad och inget CV körs. Ett fastnat CV (i gång men
-- utan framsteg sedan p_stale_before) räknas inte som körande och tas om med de andra.
-- Annars avbryts allt med felet job_ad_conflict, och ingenting har ändrats.

create function public.change_job_ad(
  p_analysis_id uuid,
  p_expected_ad text,
  p_new_ad text,
  p_stale_before timestamptz,
  p_now timestamptz
)
returns setof public.candidates
language plpgsql
as $$
begin
  -- Låser i id-ordning, så två anrop som låser samma rader inte låser sig i kors.
  perform 1 from public.candidates where analysis_id = p_analysis_id order by id for update;

  -- Statuslistan speglar IN_FLIGHT i backend/candidates.py, och villkoret om framsteg är
  -- negationen av Candidate.is_stale. Ändras det ena måste det andra ändras.
  if exists (
    select 1 from public.candidates
    where analysis_id = p_analysis_id
      and status in ('queued', 'processing')
      and last_progress_at is not null
      and last_progress_at >= p_stale_before
  ) then
    raise exception 'job_ad_conflict';
  end if;

  update public.analysis_batches
    set job_ad = p_new_ad
    where id = p_analysis_id and job_ad = p_expected_ad;
  if not found then
    raise exception 'job_ad_conflict';
  end if;

  -- Tömmer bedömningen, så ingen gammal poäng står kvar mot en annons som inte gäller.
  -- Kolumnlistan är samma som bedömningsfälten i Candidate: en ny bedömningskolumn läggs till här.
  -- Identiteten och revealed_at rörs inte: ett avslöjande består (ADR 0009).
  return query
    with claimed as (
      update public.candidates
        set status = 'queued',
            step = null,
            last_progress_at = p_now,
            score = null,
            years_experience = null,
            education_match = null,
            concrete_results = null,
            key_skills = null,
            missing_requirements = null,
            rationale = null,
            failure_reason = null
        where analysis_id = p_analysis_id
        returning *
    )
    select * from claimed;
end;
$$;

-- Som tabellerna: bara backend (service_role) når funktionen (ADR 0002).
revoke all on function public.change_job_ad(uuid, text, text, timestamptz, timestamptz)
  from public, anon, authenticated;
grant execute on function public.change_job_ad(uuid, text, text, timestamptz, timestamptz)
  to service_role;
