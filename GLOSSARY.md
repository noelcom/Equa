# Equa – ordlista

Equa är en SaaS för anonym, kompetensbaserad CV-matchning. Rekryteraren laddar upp en arbetsannons och CV:n, och får en rankad lista där människan alltid fattar beslutet.

Format: **Svensk term** (kodnamn) – definition. _Undvik:_ synonymer vi inte använder.

## Aktörer

**Kund** (`customer`) – företaget eller byrån som använder Equa. Personuppgiftsansvarig enligt GDPR. Equa är personuppgiftsbiträde. _Undvik:_ klient.

**Rekryterare** (`user`) – personen med ett konto. I v1 är ett konto en person, utan team. _Undvik:_ admin (admin är Equas ägare).

**Profil** (`profile`) – kontots inställningar och gränser: månadskvot, standard- och maxtid för radering, filstorlekstak. Ändras av Equas ägare i Supabase.

**Kandidat** (`candidate`) – personen bakom ett CV, och även dennes bedömda rad i en analys. Visas alltid som "Kandidat #N".

## Analys

**Analys** (`analysis_batch`) – en rekryteringsomgång: en arbetsannons plus de CV:n som laddats upp mot den. CV:n kan läggas till i efterhand. _Undvik:_ batch i användargränssnittet, körning.

**Arbetsannons** (`job_ad`) – texten rekryteraren klistrar in. Allt bedöms mot den.

**Anonym alias** (`anonymous_alias`) – "Kandidat #N". Det enda namn som syns i gränssnitt och export.

**Leaderboard** – alla kandidater i en analys, sorterade efter poäng. Ingen kandidat filtreras bort. Misslyckade CV:n visas i en egen sektion.

**Poäng** (`score`) – 0–100. Ett beslutsstöd, aldrig ett avvisande.

**Bedömning** – poäng, års erfarenhet, utbildningsmatch, konkreta resultat, nyckelkompetenser, saknade krav och motivering.

## Pipeline

**Förtvätt** – lokal PDF→Markdown (bilder kastas) plus regex som tar bort e-post, telefon, personnummer och webbadresser.

**AI-tvätt** – Haiku byter ut namn, adresser, ålder och könspronomen mot `[BORTTAGET]`.

**Säkerhetskontroll** – regex körs igen på tvättad text. Hittas något stoppas CV:t.

**Bedömningssteg** – Sonnet bedömer tvättad text mot annonsen, med strukturerad utdata (Pydantic).

**Kunde inte analyseras** (`failed`) – eget tillstånd för CV:n som inte kunde läsas (t.ex. inskannad bild), inte anonymiseras säkert eller inte tolkades. Aldrig poäng 0, och räknas inte mot kvoten.

## Data och gränser

**Avslöja** (`reveal`) – rekryteraren laddar ner originalfilen för en vald kandidat. Det enda sättet identiteten visas. Loggas inte.

**Raderingsdatum** (`expires_at`, TTL) – när analysen och dess originalfiler raderas automatiskt. Standard 7 dagar, valbart eget datum, tak 90 dagar.

**Kvot** (`cv_quota_limit`) – max antal lyckade CV:n per kalendermånad, standard 500. Kontrolleras före en körning.

**Användningslogg** (`usage_logs`) – permanent, anonymiserad rad per körning: kund, tid, antal CV:n, tokens. Underlag för fakturering.

**Originalfil** – den uppladdade PDF:en, lagrad krypterat tills raderingsdatum.
