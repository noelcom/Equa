# 0008 – AI-modeller och underbiträde

Status: accepterad.

## Beslut
- Anthropic är Equas enda AI-underbiträde. Andra leverantörer utreds inte förrän Anthropic misslyckas på kvalitet, pris eller dataskydd, till exempel om EU-region blir ett kundkrav.
- AI-tvätten kör Haiku 5.5 och bedömningssteget kör Sonnet 5.5. Valen ligger i `config.py`.
- Batch API används inte, för varken AI-tvätt eller bedömningssteg.
- Bedömningen är kompetensbaserad: AI:n bygger bara på det som står i CV:t mot annonsen och gissar aldrig. "Saknade krav" är konkreta gap mot annonsen, aldrig risker hos personen.
- Ett byte av modell, eller ett nytt underbiträde, kräver att kriterierna nedan klaras på ett testset.

## Kriterier för modellbyte
- **AI-tvätt:** noll missade identifierare (namn, adresser, ålder, könspronomen) och oförändrat sakinnehåll: titlar, år, siffror och kompetenser står kvar ordagrant. Missar Haiku, provas Sonnet för tvätten.
- **Bedömningssteg:** rangordningen stämmer med ägarens egen (samma topp 3), samma CV körd två gånger ger poäng som skiljer högst ±5, och motiveringen är sakligt korrekt utan påhittade erfarenheter. Klarar Sonnet inte detta provas Opus. Haiku prövas inte för bedömningssteget.

## Varför
Batch halverar priset men lämnar texten kvar hos Anthropic i 29 dagar utan zero data retention (ZDR). Det är längre än standardraderingen på 7 dagar, och "Radera direkt" når inte texten hos Anthropic. Det krockar med ADR 0007, där mindre sparad data ger mindre risk. Vinsten är ungefär 0,45 USD per 500 CV:n, och svar kan dröja upp till 24 timmar medan rekryteraren väntar.

Ett leverantörsbyte kräver ny DPA och nytt underbiträde, och pilotkunderna skriver om sina avtal. Det finns ingen oberoende kvalitetsdata för några alternativ på CV:n.

Kompetensbaserad bedömning följer ADR 0003: människan beslutar. En riskbedömning av en person är där fördomar smyger in, och den gör rekryteraren själv. Ägarens jämförelse mot piloten i #12 visade att piloten bedömde mer som en rekryterare, med risker i fokus, medan Equa bedömer kunskap. Equa ska inte gå åt det hållet.

Piloten körde Sonnet 5.5 även för AI-tvätten. Haiku 5.5 är valet för Equa eftersom uppgiften är regelnära, högvolym och har kontrollerbart utfall, och den testades mot kravet ovan i #12 utan att någon miss hittades.

Underlag: `docs/research/modellval-tvatt-och-analys.md`.

## Kvar att göra
- Kriterierna är skrivna. Konsekvenstestet (±5) körs av `backend/scripts/consistency.py` (#25). Tvättkriteriet och rangordningen (topp 3) saknar fortfarande testset.

## Konsekvenser
- Equas AI-kostnad är högre än med Batch, och rimlig vid kvoten på 500 CV:n per kund och månad.
- Fable 5.2 kan inte användas utan särskilt godkännande, eftersom den kräver 30 dagars retention.
- `inference_geo` har bara `global` och `us`. Saknad EU-region hanteras i DPA-arbetet, inte av modellvalet.
