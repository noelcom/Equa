# 0009 – Avslöjande med sparad identitet

Status: accepterad. Ersätter delar av 0007 (vad som sparas, exporten, att avslöjanden inte loggas).

## Beslut
- Rekryteraren läser anonymt och avslöjar en kandidat i taget, efter en bekräftelse. Ett avslöjande går inte att ångra och ligger kvar även om analysen körs om.
- Ett avslöjande visar namn, e-post och telefon, sparas med tidpunkt och syns i listan. Originalfilen går bara att ladda ner för avslöjade kandidater.
- Identiteten läses ut redan vid uppladdningen: namnet av AI-tvätten och e-post och telefon av förtvättens regex. Den första träffen av varje sparas.
- Vid omkörning behålls tidigare sparade fält (namn, e-post, telefon) när utläsningen missar något. En ny träff ersätter den gamla, en miss gör det inte, så en redan avslöjad identitet försvinner aldrig.
- Identiteten krypteras i backend med en egen nyckel innan den skrivs till databasen. Den skickas aldrig till webbläsaren för en kandidat som inte är avslöjad.
- Identiteten raderas med analysen, som allt annat.
- Exporten visar namn, e-post och telefon för avslöjade kandidater.
- Avslöjande och nedladdning stoppas efter raderingsdatum.

## Varför
Rekryteraren ska bedöma kompetens anonymt, men behöver veta vem personen är för att gå vidare. Att ladda ner en PDF för att se ett namn var klumpigt, och avslöjade kandidater syntes inte i listan.

Identiteten fanns redan sparad för alla kandidater, i den krypterade originalfilen med samma raderingsdatum. Att spara den en gång till i strukturerad form tillför ingen ny sorts personuppgift, och avslöjandet blir omedelbart.

Vi övervägde att läsa ut identiteten först vid avslöjandet, så att bara avslöjade kandidaters uppgifter sparas, eventuellt med e-post och telefon direkt och namnet strax efter. Det valdes bort till förmån för ett omedelbart avslöjande, eftersom uppgifterna ändå redan finns i originalfilen.

Strukturerad identitet bredvid poängen är lättare att läcka i bulk än PDF:er. Därför krypteras den i backend, så att varken en databasdump, Supabase-konsolen eller en felaktig fråga visar namn.

## Konsekvenser
- Avslöjanden sparas med tidpunkt. Ett konto har bara en person (0006), så vem som avslöjade är alltid ägaren.
- Backend behöver en krypteringsnyckel. Försvinner den går sparade identiteter inte att läsa, men originalfilerna finns kvar.
- CV:n som laddades upp innan detta saknar sparad identitet och visar "Kunde inte läsas ut". De behandlas inte om.
