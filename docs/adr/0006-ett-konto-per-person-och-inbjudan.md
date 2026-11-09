# 0006 – Ett konto per person, endast inbjudna kunder

Status: accepterad

## Beslut
- v1 har ett konto per person, utan team, organisationer eller delade analyser.
- Pilotkunder bjuds in via Supabase Auth. Ingen öppen registrering. Profilen skapas vid första inloggning med standardgränser.
- Gränser per profil (månadskvot 500, standardtid 7 dagar, maxtid 90 dagar, filstorlekstak 25 MB) ändras direkt i Supabase. Ingen adminsida i v1.
- Ingen betalintegration. Fakturering sker manuellt utifrån användningsloggen.

## Konsekvenser
Team och organisationer kan kräva schemaändring senare.
