# Equas designspråk: Studio Light

Det här gäller för allt UI i Equa, både nya sidor och ändringar i befintliga. Ett lugnt, ljust arbetsverktyg i Apple-stil, byggt för att läsa CV-data länge utan att tröttna. Förlagan är `design-inspiration/korsreferens-ux-test.html` (lokal, inte incheckad). Där den och den här filen skiljer sig gäller filen.

En ny del byggs av tokens och komponenter härifrån. Behövs något som saknas, utgå från den närmaste komponenten, och lägg sedan till det nya här så att nästa del blir likadan.

## Grundprinciper

- **90/10.** 90 % av ytan är lugn: canvas `#F5F5F7` och vita kort. De sista 10 % är sparsamma färgpunkter som visar status, val och trygghet. Färg betyder alltid något.
- **Färger kommer bara från tokens nedan.** Ingen violett eller lila, i produkten eller i marknadsmaterial.
- **Korsreferens är kärnan.** Varje påstående om en kandidat pekar till stället i originalet där det står (se *Korsreferens*). Det som saknas i originalet sägs ut i grått: "Telefon framgår inte".
- **Anonymiteten styr vad som visas.** Namn, kontaktuppgifter och liknande visas först efter **Avslöja** (se `GLOSSARY.md`). Förlagan visar namn och omaskerat original för att testa upplägget. Den delen följer inte med in i produkten.
- **Lugnt och snabbt före lekfullt.** Rörelse visar var något hamnade, aldrig mer (se *Rörelse*).

## Tokens

Det här är den enda källan till färger, radier, skuggor, typsnitt och kurvor. Skriv aldrig hex-värden direkt i en komponent.

```css
:root {
  /* Ytor */
  --equa-bg-canvas: #F5F5F7;   /* appens bakgrund bakom alla kort */
  --equa-bg-card: #FFFFFF;     /* kort, paneler, menyer */
  --equa-bg-subtle: #F2F2F5;   /* hover, inaktiva filter, taggar, vald post i sidomenyn */
  --equa-bg-track: #E8E8ED;    /* spår i staplar, ringar och segmentreglage */
  --equa-header-glass: rgba(245, 245, 247, .82); /* med backdrop-filter: blur(20px) saturate(180%) */

  /* Kanter */
  --equa-border-hairline: rgba(0, 0, 0, .07); /* 1px runt kort, fält och avdelare */
  --equa-border-strong: rgba(0, 0, 0, .14);   /* sekundärknappar, kbd */

  /* Text och primär åtgärd */
  --equa-ink: #1D1D1F;            /* rubriker, brödtext, primärknapp, tooltip, toast */
  --equa-ink-hover: #333336;
  --equa-text-secondary: #6E6E73; /* motiveringar, metadata */
  --equa-text-tertiary: #86868B;  /* etiketter i versaler, platshållare, hjälptext */

  /* Accenter */
  --equa-emerald: #157347;      /* trygghet: anonymiserat läge, uppfyllda krav */
  --equa-emerald-soft: #EAF5F0;
  --equa-ocean: #0066CC;        /* interaktion: val, fokus, korsreferens, poäng 80–100 */
  --equa-ocean-soft: #EBF4FF;
  --equa-petrol: #0F4C5C;       /* poäng 60–79 (badgeyta #E7EEF0) */

  /* Status */
  --equa-amber: #9A5B13;        /* uppmärksamhet: gallras snart, oläsbar PDF, kortlistad */
  --equa-amber-soft: #FDF4E7;
  --equa-crimson: #B83A3A;      /* bara när säkerhetskontrollen stoppar en fil */
  --equa-crimson-soft: #FDEEEE;

  /* Former */
  --equa-radius-card: 16px;     /* stora kort och paneler */
  --equa-radius-inner: 12px;    /* inre rutor, banners, hopfällbara block */
  --equa-radius-pill: 9999px;   /* knappar, sökfält, taggar, badges, segmentreglage, toast */
  --equa-shadow-card: 0 2px 12px rgba(0, 0, 0, .03);
  --equa-shadow-hover: 0 8px 24px rgba(0, 0, 0, .055);

  /* Rörelse */
  --ease-out: cubic-bezier(.23, 1, .32, 1);
  --ease-drawer: cubic-bezier(.32, .72, 0, 1); /* allt som fälls ut eller ihop */

  /* Typsnitt */
  --font-ui: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-head: "Plus Jakarta Sans", Inter, -apple-system, BlinkMacSystemFont, sans-serif;
}
```

**Poängnivåer** (`--tier`) färgar staplar, ringar och badges: 80–100 `ocean` på `ocean-soft`, 60–79 `petrol` på `#E7EEF0`, under 60 `text-tertiary` på `bg-subtle`.

**Mindre radier** för små saker: listrader 10px, tooltip, matrisrutor och menyval 8–9px, meny 14px, PDF-sidor 6px, markeringar i PDF:en 3px.

## Typografi

Inter för gränssnittet, Plus Jakarta Sans 700 med `letter-spacing: -.025em` för rubriker, siffran i poängringen och ordmärket.

| Roll | Storlek / radhöjd | Vikt och övrigt |
| :--- | :--- | :--- |
| Brödtext i appen | 13.5px / 1.45 | 400, `ink` |
| Läsbar löptext (motiveringar) | 14px / 1.55 | max ca 72ch per rad |
| Rubrik i verktygsraden | 19px / 1.2 | rubriktypsnitt, en rad med ellips |
| Rubrik i detaljpanelen | 22px / 1.15 | rubriktypsnitt |
| Avsnittsrubrik | 15px | rubriktypsnitt |
| Metadata, hjälptext | 12–12.5px | `text-secondary` eller `text-tertiary` |
| Etikett | 10.5px | 600, versaler, `letter-spacing: .07em`, `text-tertiary` |
| Tagg, badge, tooltip | 11.5px | 500 för badge |

- **Siffror har alltid `font-variant-numeric: tabular-nums`**: poäng, år, kvoter, sidnummer, räknare.
- Namn och rubriker i listor står på en rad (`white-space: nowrap` med ellips), aldrig radbrutna.
- Vikterna är 400, 500 och 600 för Inter och 600 och 700 för Plus Jakarta Sans.

## Layout

- **Skal:** tre kolumner, `248px | minmax(0,1fr) | 380px`, med 16px mellanrum och 16px kant. Sidomeny till vänster, huvudkort i mitten, detaljpanel till höger. Varje kolumn är ett vitt kort och skrollar för sig, så sidan själv skrollar inte.
- **Brytpunkter:** ≤1240px ger `220 | 1fr | 340`. ≤1060px döljer sidomenyn. ≤820px staplar allt i en kolumn, med 10px kant, och sidan skrollar. Testa på 1440 och 390px.
- **Huvudkortet:** verktygsrad överst (16px 22px, hårfin linje under) med titel och metadata till vänster och verktyg högerjusterade (`margin-left: auto`). Innehållet under har 18px 22px kant.
- **Verktyg som står still:** det som göms i ett visst läge placeras längst till vänster i den högerjusterade verktygsraden, så att resten står kvar på samma pixel. Där raden radbryts används `visibility: hidden` i stället för `display: none`.
- **Detaljpanel:** 24px kant. Avsnitt skiljs med en hårfin linje och 14px luft, utan egna kort.
- **Dokumentvy (originalet):** sidorna centreras med `max-width: 700px` på canvas. Överst en klibbig glasrad med tillbaka-knapp, var man är och stegning mellan ställen.
- Avstånd väljs ur 2, 4, 6, 8, 10, 12, 14, 16, 18, 22 och 24px.

## Komponenter

Värdena nedan är det som gäller. Förlagan har dem under klassnamnen inom parentes.

- **Kort** (`.sx-card`): `bg-card`, 1px `border-hairline`, `radius-card`, `shadow-card`.
- **Knapp** (`.sx-btn`): pill, höjd 32px (liten 28px, full bredd 38px), padding 0 15px, 500. *Sekundär:* vit med `inset 0 0 0 1px border-strong`, hover `bg-subtle`. *Primär* (`.ink`): `ink`-bakgrund och vit text, hover `ink-hover`. Högst en primär knapp per vy.
- **Liten växelknapp** (`.ia-b`): pill 22–30px med tunn kant. Nedtryckt får den statusfärgen på sin mjuka yta (kortlista: `amber` på `amber-soft`, avfärda: `ink` på `bg-track`) och tappar kanten.
- **Rund ikonknapp** (`.ra-b`, `.nt-x`, `.step button`): 24–28px cirkel, transparent, `text-tertiary`. Hover ger `rgba(0,0,0,.05)` och `ink`. Radåtgärder syns först vid hover, när raden är vald eller vid fokus, och alltid på pekskärm.
- **Sökfält** (`.sx-search`): pill, 32px, `bg-subtle` med ikon till vänster. Vid fokus blir det vitt med `inset 0 0 0 1px ocean` och en 3px `ocean-soft`-ring.
- **Segmentreglage** (`.sx-seg`): pill på `bg-track` med 3px inre kant. Valet är en vit pill med mjuk skugga som glider mellan lägena (220ms). Knappar på 28px (liten variant 24px), 12.5px, 500. Ej valda är `text-secondary`. Ett antal skrivs efter etiketten i `text-tertiary`.
- **Badge** (`.sx-badge`): pill på 22px, 11.5px, 500, mjuk yta med färgen som text. Varianter: poängnivå, `emerald` (trygghet, match), neutral (`bg-subtle` och `text-secondary`), `amber`.
- **Tagg** (`.sx-chip`): pill, 2px 9px, 11.5px, `bg-subtle`. Träff på sökt kompetens (`.hit`) blir `ocean` på `ocean-soft`.
- **Listrad** (`.sx-row`): grid, 10px 12px, radie 10px, 14px mellan kolumner. Hover ger `bg-subtle`. Den valda raden har en glidande markering i `ocean-soft` med en 3px `ocean`-stav till vänster, och ett rangnummer i `ocean` 600. Huvudraden består av etiketter med en hårfin linje under. Nedtonad rad har opacitet .32. Avfärdad rad har .42 och genomstruket namn.
- **Poängstapel** (`.sx-bar`): 6px hög, radie 3px, spår i `bg-track`, fyllning i `--tier` som växer med `scaleX`, aldrig med `width`. Siffran står till höger, 600.
- **Poängring** (`.sx-ring`): 72px, spår i `bg-track`, rundad ände i `--tier`, siffran i mitten med rubriktypsnitt 22px.
- **Mätare** (`.sx-meter`): som stapeln men fylld med `ink`. Används för kvot.
- **Kravstatus** (`.kq-dots`): 7px prickar. Uppfyllt är fylld `emerald`, delvis halvfylld, saknas en tom ring i `text-tertiary`. En kort text står bredvid: `6/6 skallkrav`.
- **Kravlista** (`.sx-reqs`): ikon, kravtext och längst till höger en liten etikett. Förklaringen till ett saknat krav står som grå undertext under kravet, inte i ett eget avsnitt.
- **Inre ruta** (`.sx-xai`, `.ct`): `radius-inner` på `bg-canvas` inne i ett vitt kort, med 10–16px kant.
- **Hopfällbart block** (`.sx-ad`): `radius-inner` med hårfin kant. Huvudet har en chevron som vrids 90°. Kroppen fälls ut med `grid-template-rows: 0fr → 1fr`, 260ms `--ease-drawer`.
- **Notis** (`.nt`): `ocean-soft`, `radius-inner`, 12px text, info-ikon i `ocean` och ett stängningskryss. Används för engångshjälp i stället för fast hjälptext. När den stängs fälls den ihop.
- **Problemlista** (`.fx-item`): rutor på `bg-subtle` med radie 10px, ikon i `amber`, filnamnet i 600 (`overflow-wrap: anywhere`) och en förklaring under.
- **Meny** (`.xp-menu`): glas (`rgba(255,255,255,.9)` med blur), radie 14px, skugga `0 0 0 1px border-hairline, 0 12px 32px rgba(0,0,0,.12)`. Den växer ut från hörnet vid knappen (`transform-origin`). Varje val har rubrik i 500 och en förklaring under i 11.5px `text-secondary`.
- **Tooltip** (`.tt`): `ink`-bakgrund, vit 11.5px text, radie 8px, högst 280px bred.
- **Toast** (`.ts`): `ink`-pill nederst i mitten, 13px, med en eventuell åtgärd som halvgenomskinlig vit pill ("Ångra").
- **Tangent** (`kbd`): 11px, radie 5px, vit med `inset 0 0 0 1px border-strong`. Kortkommandon visas i en ledtrådsrad ovanför listan (12px, `text-tertiary`).
- **Tomt läge** (`.sx-empty`): centrerad 13px `text-secondary` med 30px luft. Säg vad som saknas och vad man kan göra.
- **Glasrad** (`.cv-bar`): `header-glass` med blur, klibbig överst. Med `prefers-reduced-transparency` blir den ogenomskinlig canvas.

### Korsreferens

- **Påstående** (`.cx`): texten behåller sin färg och får en prickad understrykning, `rgba(0,102,204,.45)`, 1.5px tjock, med 3px avstånd. Hover ger `ocean-soft` och `ocean`. Nedtryckt (`aria-pressed`) ger heldragen understrykning. *Eko*, när man håller musen över markeringen i originalet, ger `rgba(0,102,204,.14)`.
- **Tagg som påstående** (`.cx.sx-chip`): istället för understrykning en `inset 0 -1.5px 0 rgba(0,102,204,.3)`. Nedtryckt blir den fylld `ocean` med vit text.
- **Utan ställe i originalet** syns ingen understrykning, ingen pekhand, och texten är grå. Det som inte går att klicka på ska inte se klickbart ut.
- **Markering i PDF:en** (`.mk`): `mix-blend-mode: multiply` så att trycket syns igenom. Aktiv `rgba(0,102,204,.2)` med en 2px `ocean`-linje under, aktuell `.3`, hover `.1`. I vänstermarginalen står en prick per citerat ställe, och det aktiva påståendets prickar växer till streck.
- Ett klick på ett påstående byter till originalet, skrollar mjukt till stället och markerar det. Det finns alltid en tydlig väg tillbaka.

## Tillstånd

- **Hover** bara under `@media (hover: hover) and (pointer: fine)`, så att den inte fastnar på pekskärm.
- **Fokus:** `:focus-visible` med `outline: 2px solid ocean` och `outline-offset: 2px`.
- **Tillstånd styrs av ARIA-attribut** och stylas på dem: `aria-pressed` (växlar), `aria-selected` (vald rad), `aria-current` (vald post i menyn). Klasser används bara för utseende som inte är ett tillstånd.
- **Tryck:** se *Rörelse*.

## Text i gränssnittet

- Svenska, kort och saklig. Knappar säger vad som händer ("Exportera", "Visa vem det är").
- Räkna med det användaren bryr sig om: `5 bedömda CV`. Visa två siffror (`6 CV · 5 bedömda`) bara när de skiljer sig.
- Saknade uppgifter sägs ut i grått, aldrig som en tom rad: "Språknivån framgår inte".

## Rörelse

Kurvan är `--ease-out`. Färgbyten vid hover tar 150ms `ease-out`. Innehåll som byts tonar in med `translateY(4px)` på 220ms. Det som fälls ut använder `--ease-drawer` på 240–260ms. Animera `transform` och `opacity`, aldrig bredd eller höjd.

- **Kortkommandon animerar aldrig.** ↑↓, ←→, S, Esc, Enter och andra tangentbordsgenvägar ändrar skärmen i samma bildruta: inga glidningar, ingen tonande in-animation, inga blinkningar, inga studsar och inga färgövergångar. Samma handling med musen får behålla en kort rörelse (≤ 260 ms, `var(--ease-out)`) när rörelsen visar var något hamnade, till exempel att radmarkeringen glider till den klickade raden. Funktioner tar en boolesk flagga (`viaKey`/`instant`) som slår av rörelsen, inga globala flaggor.
  Varför: den som använder tangentbordet arbetar snabbt och trycker samma tangent om och om igen. Animation gör att verktyget känns segt, och man hinner trycka igen innan förra rörelsen är klar.
  <!-- 2026-11-21: "Kör planerna 001 → 004" och "Gör alla åtta", godkänt efter förklaringen "med tangentbordet sker allt direkt" -->

- **Poängen och andra siffror som rekryteraren läser byts direkt när man byter kandidat.** De räknar aldrig upp eller ned vid byte. Uppräkning från 0 är tillåten bara när sidan laddas första gången.
  Varför: poängen är det första man läser, och en siffra som räknar går inte att läsa förrän den stannat.
  <!-- 2026-11-21: "Lite synd att animationen med poäng hjulet försvinner men men", rekommendationen att behålla det direkta bytet accepterades; ompröva om UX-testet säger att panelen känns stel -->

- **Toggle-knappar (kortlista, avfärda och liknande) studsar aldrig.** Återkopplingen är intrycket och att tillståndet ändras, till exempel färg och `aria-pressed`. Ingen keyframe-animation på själva togglingen.
  Varför: trycket ger redan återkoppling, och en keyframe startar om och rycker när man klickar snabbt.
  <!-- 2026-11-21: "Gör alla åtta" (studsen på stjärnan togs bort) -->

- **Tryckåterkoppling: `:active { transform: scale(.95) }` eller grundare (`.95`–`.98`), med `transition: transform 160ms var(--ease-out)`.** Aldrig djupare än `.95`, och aldrig med inbyggd `ease-out`.
  Varför: djupare tryck känns lekfulla, och Equa är ett lugnt arbetsverktyg.
  <!-- 2026-11-21: "Gör alla åtta" (.88/.9/.92 → .95, 120ms ease-out → 160ms var(--ease-out)) -->

- **När en lista laddas in en rad i taget är taket 10 rader:** `animation-delay: calc(min(var(--i), 10) * 30ms)`. Hela entrén, staplar inräknade, är klar inom ungefär 0,5 s oavsett antal rader.
  Varför: rekryteraren ska inte vänta på att en lång lista kommer fram.
  <!-- 2026-11-21: "Gör alla åtta" (24ms × rad utan tak, staplar 620/700 ms → tak 10 × 30ms, staplar 400/450 ms) -->

- **Tooltips: den första visas efter en fördröjning. Är en tooltip redan uppe, eller stängdes för mindre än 500 ms sedan, visas nästa direkt, utan fördröjning och utan att tona in.**
  Varför: den som flyttar musen mellan flera saker vill läsa dem i rad, inte vänta på varje.
  <!-- 2026-11-21: "Gör alla åtta" -->

- **Med `prefers-reduced-motion: reduce` tas förflyttning och skalning bort, men opaciteten behålls.** Innehåll som byts tonar in på 200 ms utan fördröjning mellan rader. Ren rörelse, som staplar som växer och studsar, stängs av helt. Aldrig `* { animation: none }` över allt. Tysta omritningar förblir tysta.
  Varför: att stänga av allt gör att innehåll dyker upp utan övergång och att markeringen som visar var man hamnade försvinner.
  <!-- 2026-11-21: "Kör planerna 001 → 004" (plan 004) -->

## Interaktion

- **En lista där varje rad har en egen detaljvy eller ett eget dokument (kandidater, analyser och liknande): Enter och dubbelklick på raden öppnar det, och Esc går tillbaka.** Dubbelklick på knappar inne i raden (stjärna, kryss, taggar, matrisrutor) öppnar inte detaljvyn. Ett dubbelklick markerar inte text i raden (`preventDefault` på `mousedown` när `detail > 1`, inte `user-select: none`, så att man fortfarande kan dra och kopiera). Enter gör ingenting när fokus står på en knapp eller när den valda raden är bortfiltrerad. Genvägen står i ledtrådsraden ovanför listan.
  Varför: "kommer öka snabbheten för användaren."
  <!-- 2026-11-21: "kan dubbelklicka på en rad (en person) med musen för att få upp cv:et direkt, också att man kan klicka enter för att få upp den" -->

- **Listor bläddras med ↑↓, ställen i originalet stegas med ←→, och Esc rensar eller går tillbaka.**

## Logotyp

Två överlappande ihåliga rundade kvadrater (`48×48` viewBox, `rx="6.5"`, `stroke-width="3.2"`) med en ifylld skärningslins. Den står för korsreferensen mellan annonsen och CV:t. Ordmärket **Equa** är Plus Jakarta Sans 700 med `letter-spacing: -.035em`.

- **I appen och som favicon:** allt i `ink`. På mörk bakgrund blir allt vitt.
- **I marknadsföring** (equa.se, LinkedIn, presentationer): linsen i `emerald`, resten i `ink`.
- **App-ikonens bricka:** radie 22 % av bredden.
