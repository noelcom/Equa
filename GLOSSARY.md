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

**Förtvätt** – lokal PDF→text (ren text, ingen Markdown, bilder kastas) plus regex som tar bort e-post, telefon, personnummer och webbadresser.

**AI-tvätt** – Haiku byter ut namn, adresser, ålder och könspronomen mot `[BORTTAGET]`.

**Säkerhetskontroll** – regex körs igen på tvättad text. Hittas något stoppas CV:t.

**Omförsök** – tillfälliga AI-fel (429, timeout, 5xx) provas om med växande väntetid innan CV:t blir `failed`.

**Bedömningssteg** – Sonnet bedömer tvättad text mot annonsen, med strukturerad utdata (Pydantic).

**Kunde inte analyseras** (`failed`) – eget tillstånd för CV:n som inte kunde läsas (t.ex. inskannad bild), inte anonymiseras säkert (även när AI-tvätten ger tomt svar eller vägrar), inte tolkades eller inte kunde bedömas för att AI-tjänsten var tillfälligt otillgänglig efter flera försök. Aldrig poäng 0, och räknas inte mot kvoten.

**Fastnat CV** – ett CV som stått som `queued`/`processing` längre än 15 minuter utan framsteg (`last_progress_at`, en hjärtslagsstämpel som uppdateras vid varje steg). Rekryteraren kan ta om det via "Ta om fastnade CV:n" (`/run`).

## Data och gränser

**Avslöja** (`reveal`) – rekryteraren laddar ner originalfilen för en vald kandidat. Det enda sättet identiteten visas. Loggas inte.

**Raderingsdatum** (`expires_at`, TTL) – när analysen och dess originalfiler raderas automatiskt. Standard 7 dagar, valbart eget datum. Taket är 90 dagar från den dag datumet sätts, så kunden kan förlänga aktivt hur många gånger som helst. Raderingen går igenom även mitt i en körning.

**Kvot** (`cv_quota_limit`) – max antal lyckade CV:n per kalendermånad, standard 500. Kontrolleras före en körning, när en analys skapas och när CV:n läggs till (analysens ej körda CV:n plus de nya), så det som laddas upp också går att köra. Ett CV är lyckat först när bedömningen är sparad, så ett CV vars analys raderades under körningen räknas inte.

**Återstående kvot** – kvoten minus månadens lyckade CV:n och de reserverade. Det är siffran som avgör om något får laddas upp eller köras.

**Reserverad** – ett CV som körs just nu och tillfälligt räknas av från kvoten tills utfallet är känt. Lyckas det räknas det som förbrukat, misslyckas det frigörs platsen. Uppladdade men ej körda CV:n är inte reserverade. _Undvik:_ låst, pågående förbrukning.

**Väntande** (`pending`) – uppladdade men ej körda CV:n över alla kundens analyser. Visas i profilrutan som information och påverkar ingen kontroll, så kunden kan förbereda kommande analyser. _Undvik:_ reserverad.

**Körbara CV:n** (`runnable_count`) – de CV:n i en analys som nästa körning tar: uppladdade, plus fastnade. Backend jämför dem mot återstående kvot och svarar `can_run` och `addable_count`, så gränssnittet bara visar svaret.

**Användningslogg** (`usage_logs`) – permanent, anonymiserad rad per bearbetat CV: kund, tid, om det lyckades (`cv_count` 0 eller 1), tokens. Raden skrivs så fort CV:t är klart, så ett lyckat CV räknas mot kvoten redan medan resten av körningen pågår. Underlag för fakturering.

**Originalfil** – den uppladdade PDF:en, lagrad krypterat tills raderingsdatum.
