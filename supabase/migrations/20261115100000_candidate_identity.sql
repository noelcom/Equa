-- Avslöja: kandidatens identitet och när den avslöjades (ADR 0009, GLOSSARY: Avslöja).
--
-- Identiteten krypteras i backend med en egen nyckel innan den skrivs hit, så varken en
-- databasdump, Supabase-konsolen eller en felaktig fråga visar namn i klartext. Den
-- raderas med analysen via cascade, som allt annat.

alter table public.candidates
  add column identity_encrypted text,
  -- Satt en gång och ändras aldrig: ett avslöjande går inte att ångra, inte heller när
  -- analysen körs om.
  add column revealed_at timestamptz;
