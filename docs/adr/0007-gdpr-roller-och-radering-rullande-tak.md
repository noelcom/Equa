# 0007 – GDPR-roller och radering, med rullande tak

Status: accepterad. Ersätter 0004.

## Beslut
- Equa är personuppgiftsbiträde, kunden är personuppgiftsansvarig. Anthropic och Supabase är underbiträden. Pilotkunder signerar ett personuppgiftsbiträdesavtal (DPA) före konto.
- Vi sparar bara bedömningsresultat och originalfil, aldrig tvättad text.
- Standardradering 7 dagar, valbart eget datum. Radering är automatisk och kan inte stängas av. Den tar bort databasrader och originalfiler.
- **Taket är 90 dagar räknat från idag, inte från när analysen skapades.** Varje gång kunden sätter ett nytt raderingsdatum får det ligga högst 90 dagar fram. Kunden kan förlänga hur många gånger som helst, men bara genom ett aktivt val. Gör kunden ingenting raderas analysen på datumet.
- En profil kan ha ett lägre tak än 90 dagar, aldrig högre. Förvalet sänks tyst till taket om det ligger över.
- En analys kan köras flera gånger under sin livstid (CV:n läggs till, fastnade CV:n tas om), så en körning kan pågå när analysen raderas. Raderingen väntar inte in körningen och vägras inte. Det gäller främst "Radera direkt" strax efter att rekryteraren tryckt "Kör", men även när raderingsdatum passerar mitt i en körning. Ett CV vars resultat inte kunde sparas för att analysen raderats räknas inte mot kvoten. Tokens loggas ändå i användningsloggen.
- Exporten visar bara "Kandidat #N", aldrig originalfilnamn.
- Avslöjanden loggas inte.

## Varför
Mindre sparad data ger mindre risk. 0004 räknade taket från skapandet, så en analys kunde aldrig leva längre än 90 dagar. Rekryteringar kan dra ut på tiden, och då ska kunden, som personuppgiftsansvarig, kunna behålla sin analys. Skyddet mot obestämd lagring ligger nu i att inget ligger kvar av sig självt: utan ett aktivt val minst var 90:e dag raderas analysen.

Vi övervägde ett absolut tak ovanpå, till exempel 12 månader från skapandet. Det valdes bort. Kravet på aktiv förlängning räcker som skydd, och ett absolut tak skulle slå mot kunder med långa rekryteringar.

Radering mitt i en körning vägras inte (409), eftersom det skulle hindra kunden från att radera känslig data direkt och kräva specialfall för fastnade CV:n. Pipelinen skriver bara mot befintliga rader och återskapar aldrig data, så den tål att analysen försvinner.

## Konsekvenser
- En analys kan i princip leva hur länge som helst, men bara om kunden förlänger den aktivt minst var 90:e dag.
- Ett högre tak än 90 dagar per förlängning kräver en ny ADR.
- Kunden kan inte få gratis resultat genom att radera mitt i en körning: allt som syns har sparats och räknas mot kvoten. Det enda som går förlorat är Equas AI-kostnad, och den syns i användningsloggen.
