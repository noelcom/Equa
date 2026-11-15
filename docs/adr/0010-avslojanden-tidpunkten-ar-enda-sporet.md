# 0010 – Avslöjanden: tidpunkten är enda spåret

Status: accepterad. Ersätter punkten "Avslöjanden loggas inte" i 0007 och förtydligar 0009, som strök den utan att säga vad som gäller i stället.

## Beslut
- Det enda spåret av ett avslöjande är tidpunkten (`revealed_at`) på kandidaten. Den raderas med analysen.
- Avslöjanden skrivs inte till `usage_logs`, till någon revisionslogg eller till applikationsloggen.
- Nedladdning av originalfilen lämnar inget eget spår. Den går bara efter avslöjandet, så tidpunkten täcker den.
- Vem som avslöjade behöver inte sparas: ett konto har bara en person (0006).

## Varför
Mindre sparad data ger mindre risk (0007). Tidpunkten behövs ändå för att visa "Avslöjad <datum>" i listan, och en separat logg skulle ge ett andra ställe där det syns vilka kandidater rekryteraren tittat på, utan att tillföra något.

## Konsekvenser
- `test_reveal_is_not_logged` skyddar regeln mot att loggrader smyger in.
- Behövs revision av vem som sett vad, till exempel om ett konto får flera användare, kräver det en ny ADR.
