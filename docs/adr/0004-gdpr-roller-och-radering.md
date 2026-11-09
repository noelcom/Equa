# 0004 – GDPR-roller och radering

Status: accepterad

## Beslut
- Equa är personuppgiftsbiträde, kunden är personuppgiftsansvarig. Anthropic och Supabase är underbiträden. Pilotkunder signerar ett personuppgiftsbiträdesavtal (DPA) före konto.
- Vi sparar bara bedömningsresultat och originalfil, aldrig tvättad text.
- Standardradering 7 dagar, valbart eget datum, **tak 90 dagar**. Radering är automatisk och kan inte stängas av. Den tar bort databasrader och originalfiler.
- Exporten visar bara "Kandidat #N", aldrig originalfilnamn.
- Avslöjanden loggas inte.

## Varför
Mindre sparad data ger mindre risk. Kunden väljer själv hur länge den vill ha kvar data, inom ett tak som hindrar obestämd lagring.

## Konsekvenser
Taket (90 dagar) och förvalet kan ändras per profil, men aldrig över systemets tak. Ett högre tak kräver en ny ADR.
