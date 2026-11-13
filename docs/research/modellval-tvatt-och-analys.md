# Modellval för tvätt och analys

Hämtat och sammanställt 2026-11-13. Alla länkar nedan hämtades den dagen om inget annat anges. Underlag för issue #12 ("Jämför pipeline mot pilot och lås modellval").

Frågan: vilka modeller passar för **tvätt** respektive **analys** i Equa, och vad skiljer dem i kostnad, kvalitet och hastighet?

Dokumentet skiljer på **Fakta** (citerat eller återgivet från leverantörens egen sida, med källa) och **Slutsats** (min bedömning, märkt som sådan). Det som inte gick att verifiera står som "ej verifierat".

## 1. Vad tvätt och analys är i Equa

Källor: `GLOSSARY.md`, `backend/src/equa_backend/pipeline.py`, `backend/src/equa_backend/config.py`, ADR 0002, 0003, 0007.

- **Tvätt = AI-tvätt.** Efter en lokal förtvätt (PDF till ren text, regex för e-post, telefon, personnummer, webbadresser) skickas hela CV-texten till en modell som returnerar samma text med namn, adresser, ålder och könspronomen utbytta mot `[BORTTAGET]`. Därefter en regex-säkerhetskontroll. Anropet är `client.messages.create(model=settings.wash_model, max_tokens=8192, ...)` och returnerar fri text. Utdata är ungefär lika lång som indata (hela CV:t skrivs om), så tvätten är **utdatatung**.
- **Analys = bedömningssteget.** Modellen bedömer tvättad text mot arbetsannonsen och returnerar ett Pydantic-schema (`Assessment`: poäng 0-100, år, utbildning, resultat, kompetenser, saknade krav, motivering) via `client.messages.parse(..., output_format=Assessment)`, `max_tokens=2000`. System-prompten och annonsen cachas med `cache_control: ephemeral` eftersom de är gemensamma för alla CV:n i en analys.
- **Nuvarande modellval** (`config.py`): `wash_model = "claude-haiku-5-5"`, `assessment_model = "claude-sonnet-5-5"`. Kommentaren säger att valet "låses efter jämförelse mot piloten (#12)". `docs/reference/pilot.py` använder `claude-sonnet-5-5` för båda stegen.
- **Krav som styr valet:** människan beslutar och ingen sorteras bort (ADR 0003), så ett orättvist lågt poäng pga trunkerat eller tomt svar är värre än ett fel; misslyckade CV:n blir `failed`, aldrig poäng 0. Tvättad text sparas aldrig (ADR 0007). Anthropic är underbiträde under DPA (ADR 0007). Kvot standard 500 lyckade CV:n per kund och månad.
- Inget annat LLM-anrop finns i koden (sökt i `backend/src`).

## 2. Fakta: Anthropics modeller

### 2.1 Specifikation och pris (Claude API, standard)

Källor: [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) och [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (docs.claude.com omdirigerar hit), samt modellsidorna för [Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview), [Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview), [Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview) och [Fable 5.2](https://platform.claude.com/docs/en/models/fable-5-2/overview). Alla hämtade 2026-11-13.

Pris i USD per miljon tokens (MTok).

| | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 | Fable 5.2 |
|---|---|---|---|---|
| Model-ID | `claude-haiku-5-5` | `claude-sonnet-5-5` | `claude-opus-5-5` | `claude-fable-5-2` |
| Utgiven | 2026-10-07 | 2026-09-28 | 2026-09-22 | 2026-11-09 |
| Input | 0,10 (prompt över 100 000 tokens: 0,50) | 2 | 4 | 8 |
| Output | 0,50 (över 100 000: 2,50) | 10 | 20 | 40 |
| Batch input / output (-50 %) | 0,05 / 0,25 (över 100 000: 0,25 / 1,25) | 1 / 5 | 2 / 10 | 4 / 20 |
| Cache-skrivning 5 min | 0,125 | 2,50 | 5 | 10 |
| Cache-skrivning 1 h | 0,20 | 4 | 8 | 16 |
| Cache-träff | 0,01 (0,1x) | 0,10 (0,05x) | 0,20 (0,05x) | 0,20 (0,025x) |
| Kontextfönster | 1M | 1M | 1M | 1M |
| Max output (synkront) | 128K | 128K | 128K | 128K |
| Latens (Anthropics jämförande skala) | Fastest | Fast | Moderate | Moderate |
| Thinking | Adaptive | Adaptive | Adaptive (alltid på) | Adaptive (alltid på) |
| Standardnivå för `effort` | `medium` | `high` | `medium` | `high` |
| Lägsta cachebara prompt | 512 tokens | 512 tokens | 512 tokens | ej verifierat |
| Fast mode (upp till 2,5x output tokens/s) | nej | nej | ja, 8 / 40 | ja, 16 / 80 |
| Pensionering | tidigast 2027-10-07 | tidigast 2027-09-28 | tidigast 2027-09-22 | tidigast 2027-11-09 |

Anteckningar från källorna:

- Haiku 5.5 prissätts efter promptlängd: en request med över 100 000 inputtokens (inklusive cacheläsningar och cacheskrivningar) betalar de högre priserna. Övriga Claude 4.6+-modeller har full 1M-kontext till standardpris ([Pricing, Long context pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Ett CV ligger långt under 100 000 tokens, så det är inget som slår mot Equa i normalfallet.
- Ny tokenizer: "Claude 4.7 and later models ... produces approximately 30% more tokens for the same text" jämfört med äldre ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)). Haiku 5.5 räknar ca 30 % fler tokens än Haiku 4.5 för samma text ([What's new in Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5)). Ej verifierat hur tokenizern beter sig på svensk text.
- Batch- och cacherabatter staplas ("Batch API and prompt caching discounts can be combined", [Pricing FAQ](https://platform.claude.com/docs/en/about-claude/pricing)). `inference_geo: "us"` ger 1,1x på alla priser ([Data residency](https://platform.claude.com/docs/en/manage-claude/data-residency)).
- Haiku 5.5:s cacheträff är 10 % av input (0,01 av 0,10). Sonnet 5.5 och Opus 5.5 har 5 %, Fable 5.2 2,5 % ([Pricing](https://platform.claude.com/docs/en/about-claude/pricing)).

### 2.2 Funktioner som Equa använder

| Funktion | Fakta | Källa |
|---|---|---|
| Structured outputs (`output_format` / `messages.parse`) | Stöds av `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` med flera. Status "stable". Rekursiva scheman, numeriska gränser (`minimum`/`maximum`), stränggränser och `additionalProperties` annat än `false` stöds inte (400-fel). Kompilerad grammatik cachas 24 h. Inputräkningen blir "slightly higher". Ändrad `output_config.format` ogiltigförklarar promptcachen för tråden. Fable 5.2 ingick inte i den lästa modelllistan (sidan kapades, ej verifierat). | [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) |
| Batch API | 50 % rabatt på input och output. "most batches completing within 1 hour", men upp till 24 h innan de förfaller. Max 100 000 requests eller 256 MB per batch. Resultat kan hämtas i 29 dagar. Alla fyra modellerna stöds. **Inte ZDR-berättigat: "29-day retention; async storage required".** | [Batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing) |
| Prompt caching | 5 min-skrivning 1,25x, 1 h-skrivning 2x, läsning 0,1x av input på de flesta modeller (se tabellen ovan för 5.5-modellerna). Lönar sig efter en läsning (5 min) respektive två (1 h). | [Pricing, Prompt caching](https://platform.claude.com/docs/en/about-claude/pricing) |
| Effort | `output_config.effort` med `low`, `medium`, `high`, `xhigh`, `max` på alla fyra. Påverkar alla output-tokens, inklusive tänkande. "Tuning effort is often a better lever than switching models." | [Effort](https://platform.claude.com/docs/en/build-with-claude/effort), [Choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model) |
| Stänga av thinking | Haiku 5.5: `thinking: {"type": "disabled"}` fungerar vid `high` eller lägre. Sonnet 5.5: `disabled` ger 400, använd `thinking: {"type": "between_tools"}` (vid `high` eller lägre). Opus 5.5 och Fable 5.2: går inte att stänga av. | [Effort](https://platform.claude.com/docs/en/build-with-claude/effort), [What's new in Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5) |
| Samplingparametrar | `temperature`, `top_p`, `top_k` ska utelämnas (Haiku 5.5, Fable 5.2) respektive ger 400 (Sonnet 5.5). Alltså går "deterministisk tvätt" inte att styra med temperature 0 på dessa modeller. Koden sätter ingen temperature, vilket är rätt. | modellsidorna ovan |
| Tvingad tool use | Ger 400 på Sonnet 5.5 och Fable 5.2. Irrelevant för Equa (använder `output_format`, inte `tool_choice`). | [What's new in Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5), [Fable 5.2](https://platform.claude.com/docs/en/models/fable-5-2/overview) |
| Refusals | Haiku 5.5 kör säkerhetsklassificerare som kan ge `stop_reason: "refusal"` (kategorier `cyber`, `frontier_llm`, `bio`, `general_harms`; Haiku 4.5 gav inte sådana). Haiku 5.5 har ingen server-side fallback. Sonnet 5.5 har fallback i beta för `cyber` och `frontier_llm`. | [Prompting Haiku 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5), [What's new in Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5) |

### 2.3 Dataskydd och region (påverkar vilka modeller som är möjliga)

Källor: [API and data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention), [Data residency](https://platform.claude.com/docs/en/manage-claude/data-residency), [Fable 5.2-annonsen](https://www.anthropic.com/claude-fable-and-mythos-5-2).

- Fable 5.2 är en "Covered Model": "require 30-day data retention and are not available under ZDR unless expressly authorized by Anthropic". Annonsen nämner att berättigade enterprisekunder kan få ZDR innan "Enterprise Frontier Safeguards" (privat beta), övriga har "30-day retention for safety monitoring". Haiku 5.5, Sonnet 5.5 och Opus 5.5 listas inte som Covered Models.
- Effort, structured outputs (kvalificerat) och data residency är ZDR-berättigade för icke-Covered-modeller. Batch är inte det.
- Inferensregion: bara `"global"` (standard) och `"us"` finns. Det finns **ingen EU-region** i `inference_geo`, och workspace geo är bara `"us"`. `"us"` kostar 1,1x. (Bedrock och Google Cloud-hostade varianter styrs av endpoint, ej verifierat för EU-regioner här.)
- Standardretentionen för vanlig Messages API utan ZDR-avtal hämtades inte (hänvisar till privacy.claude.com). Ej verifierat.

### 2.4 Kvalitet: vad leverantören själv har publicerat

Alla siffror är Anthropic-rapporterade (annonssidor, [Optimizing for cost and intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)). Inget av det är mätt på CV-tvätt eller CV-matchning. Ingen oberoende verifiering har hämtats.

| Mått | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 | Fable 5.2 | Källa |
|---|---|---|---|---|---|
| GDPval-AA v2.1 (kunskapsarbete, Elo) | 1620 | 1840 / 1844 | 1846 | ej angivet | [Haiku 5.5](https://www.anthropic.com/claude-haiku-5-5), [Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5) |
| AA-Briefcase (Elo) | 1578 (v1.1) | 1824 / 1811 | 1822 | 1785 (Opus 5.5: 1800 i samma tabell) | samma, [Fable 5.2](https://www.anthropic.com/claude-fable-and-mythos-5-2) |
| Humanity's Last Exam, med verktyg | 57,4 % | 64,5 % | 67,7 % | 74,2 % | samma |
| GPQA Diamond | 85 % | 91 % | 91 % | ej angivet | [Optimizing for cost and intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence) |

Anmärkningar:

- Sonnet 5.5-siffrorna skiljer något mellan Haiku-annonsen (1840) och Sonnet-annonsen (1844). Båda återges som publicerade. Sonnet-annonsen noterar att Artificial Analysis körde GDPval-AA och AA-Briefcase på en pre-release-build med en sedan åtgärdad bugg som påverkade structured outputs.
- Anthropic skriver att Opus 5.5 "remains clearly stronger at complex, open-ended work requiring sustained judgment" än Sonnet 5.5 ([Sonnet 5.5-annonsen](https://www.anthropic.com/claude-sonnet-5-5)), och att Haiku 5.5 är "best suited to more narrowly scoped tasks" ([Haiku 5.5-annonsen](https://www.anthropic.com/claude-haiku-5-5)).
- Anthropics positionering: Haiku 5.5 "for high-volume, latency-sensitive tasks such as classification, extraction, and routing"; Sonnet 5.5 "best combination of speed and intelligence" för bland annat dataanalys; Opus 5.5 för långkörande agentiskt arbete; Fable 5.2 "for demanding reasoning and long-horizon agentic work" ([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)).
- På GPQA Diamond kostade Haiku 5.5 "about a twentieth of Claude Opus 5.5's cost per correct answer and about a tenth of Claude Sonnet 5.5's" ([Optimizing for cost and intelligence](https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence)). Samma sida: "Claude Haiku 5.5 suits high-volume and latency-sensitive work with checkable outputs."
- Fable 5.2 jämfört med Opus 5.5 vinner på de flesta men inte alla mått (AA-Briefcase Elo: 1785 mot 1800). Anthropic anger att Fable 5.2 kostar ungefär hälften per uppgift på FrontierCode vid High effort ([Fable 5.2-annonsen](https://www.anthropic.com/claude-fable-and-mythos-5-2)), vilket gäller kodning, inte CV-bedömning.

### 2.5 Hastighet

- Anthropic publicerar bara en **relativ skala** (Fastest, Fast, Moderate, Moderate), ingen tokens/s eller tid till första token per modell: "Actual latency depends on prompt length, output length, and thinking effort" ([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)). Absoluta siffror: ej verifierat.
- Fast mode ger "up to 2.5x higher output tokens per second" på Opus 5.5 och Fable 5.2, till 2x pris, och är inte tillgängligt med Batch API ([Fast mode](https://platform.claude.com/docs/en/build-with-claude/fast-mode)).
- Sonnet 5.5 genererar output "30%+ faster" än Sonnet 5 ([Sonnet 5.5-annonsen](https://www.anthropic.com/claude-sonnet-5-5)). Kundcitat om Haiku 5.5 (Box: ungefär halva latensen mot Haiku 4.5) är anekdotiska och Anthropic-valda ([Haiku 5.5-annonsen](https://www.anthropic.com/claude-haiku-5-5)).
- **Tänkande slår igenom på latens och kostnad.** Thinking är på som standard på alla fyra, tänketokens faktureras som output och räknas mot `max_tokens` ([Haiku 5.5 what's new](https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5), [Effort](https://platform.claude.com/docs/en/build-with-claude/effort)). Hur mycket det blir på Equas uppgifter är ej verifierat.

## 3. Andra leverantörer (kort, begränsat)

Equas ADR 0007 och DPA-upplägget bygger på Anthropic som enda underbiträde. Ett leverantörsbyte skulle kräva ny DPA och ny granskning, så jag har hållit jämförelsen kort.

OpenAI:s egen prisida ([developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing)): GPT-6 Luna 0,10 input / 0,50 output / 0,01 cachad input (kort kontext, högst 272K input), GPT-6 Sol 2 / 10 / 0,20. Batch: Luna 0,05 / 0,25, Sol 1 / 5. Alltså samma listpris som Haiku 5.5 respektive Sonnet 5.5 för korta prompter. Sidan anger inget kontextfönster och inga kvalitetssiffror. Kvalitet jämfört med Claude: ej verifierat mot OpenAI-källa. Anthropics Haiku 5.5-annons jämför mot GPT-6 Luna (GDPval-AA 1620 mot 1437), men det är en konkurrents egen jämförelse och inte en primärkälla för OpenAI-modellen. Google/Gemini: ej undersökt.

## 4. Räkneexempel (illustration, inte mätning)

Antaganden som jag själv gör, inte hämtade från någon källa: ett CV på 3 000 tokens, tvättens utdata lika lång (3 000 tokens), bedömningsprompt 400 tokens, annons 800 tokens, bedömningens utdata 600 tokens, **ingen** thinking-kostnad medräknad, ingen caching. Priserna är från tabellen i 2.1. Faktisk tokenräkning på svenska CV:n och faktisk thinking-förbrukning är ej verifierade.

| Steg och modell | Standard per CV | Batch per CV | Per 500 CV:n (standard) |
|---|---|---|---|
| Tvätt, Haiku 5.5 | 0,0018 USD | 0,0009 USD | 0,90 USD |
| Tvätt, Sonnet 5.5 | 0,036 USD | 0,018 USD | 18 USD |
| Tvätt, Opus 5.5 | 0,072 USD | 0,036 USD | 36 USD |
| Tvätt, Fable 5.2 | 0,144 USD | 0,072 USD | 72 USD |
| Analys, Haiku 5.5 | 0,0007 USD | 0,0004 USD | 0,36 USD |
| Analys, Sonnet 5.5 | 0,0144 USD | 0,0072 USD | 7,20 USD |
| Analys, Opus 5.5 | 0,0288 USD | 0,0144 USD | 14,40 USD |
| Analys, Fable 5.2 | 0,0576 USD | 0,0288 USD | 28,80 USD |

Nuvarande val (Haiku-tvätt + Sonnet-analys) blir med dessa antaganden ca 0,016 USD per CV före tänkande. Absolutnivån är liten i förhållande till en kvot på 500 CV:n per månad. Tvätten är utdatatung, så dess kostnad domineras av utdatapriset. Cachning av prefixet (instruktion + annons) sänker bara analysens input, som är den mindre delen här.

## 5. Observationer om nuvarande kod mot dokumentationen

Det här är iakttagelser från att läsa koden mot de citerade sidorna, inte testade fel.

1. **`max_tokens` och thinking.** Thinking är på som standard på Haiku 5.5 och Sonnet 5.5, och "counts toward `max_tokens`" ([Prompting Haiku 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5), [Effort](https://platform.claude.com/docs/en/build-with-claude/effort)). Haiku 5.5-sidan varnar uttryckligen: "A `max_tokens` value sized for Claude Haiku 4.5 requests that ran without thinking can cut the reply off". `_wash` använder `max_tokens=8192` och tolkar `stop_reason == "max_tokens"` som "CV:t var för långt för att anonymiseras". `_assess` använder `max_tokens=2000` på Sonnet 5.5 med standardnivån `high`. Om tänkandet äter budgeten kan ett fullt rimligt CV bli `failed` med missvisande orsak, eller ett bedömningssvar avklippas. Behöver testas på riktiga CV:n (se avsnitt 7).
2. **Effort sätts inte.** Koden sätter varken `effort` eller `thinking`. Det innebär `medium` på Haiku (default) och `high` på Sonnet (default). Dokumentationen rekommenderar uttryckligen att man "Run an effort sweep on your own evals" och att effort ofta är bättre spak än modellbyte.
3. **Refusal-hantering finns för tvätten** (`stop_reason == "refusal"` ger "Kunde inte anonymiseras säkert."), men inte explicit i `_assess`. Haiku 5.5 introducerade klassificerare som Haiku 4.5 inte hade. Sonnet 5.5 har dem också. Hur ofta ett CV triggar `general_harms` är ej verifierat.
4. **Batch API är inte ZDR-berättigat och behåller resultat 29 dagar.** ADR 0007 säger att tvättad text aldrig sparas hos Equa. Att skicka tvättat eller otvättat CV-innehåll via Batch skulle lägga text hos Anthropic i 29 dagar utanför Equas raderingsjobb. Detta strider inte nödvändigtvis mot ADR:en (som gäller Equas egen lagring), men det är en DPA- och GDPR-fråga som beslutas av användaren.

## 6. Slutsatser (min bedömning, inte citerade fakta)

### Tvätt

**Rekommendation: behåll Haiku 5.5 som förval, med Sonnet 5.5 som jämförelsemodell i #12.**

- Uppgiften är regelnära, högvolym och har kontrollerbart utfall (regex-säkerhetskontrollen efteråt, plus ett manuellt stickprov), vilket är det Anthropic själva beskriver som Haikus användningsområde. Kostnaden är ungefär 20 gånger lägre än Sonnet och 40 gånger lägre än Opus i räkneexemplet. Latensen är lägst i Anthropics skala.
- Det som kan tala emot Haiku är risken att den missar en namnförekomst (till exempel namn i fritext, referenser, förenings- eller företagsnamn som identifierar en person) eller ändrar sakinnehåll. Regex fångar bara kontaktuppgifter, inte namn. Om stickprovet visar missar är nästa steg Sonnet 5.5 på tvätten, inte Opus eller Fable.
- Opus 5.5 och Fable 5.2 motiveras inte för tvätt: ingen beskriven fördel för uppgiften, 40 respektive 80 gånger dyrare än Haiku (räkneexemplet), och Fable 5.2 kräver dessutom 30 dagars retention.
- Låt tvätten köra med lågt eller stängt tänkande (`effort: "low"` eller `thinking: disabled`, som Haiku 5.5 tillåter vid `high` eller lägre) och höj `max_tokens`, så att budgeten inte går åt till tänkande. Detta är en hypotes att testa, inte ett belagt råd för just tvätt.
- Batch (-50 %) passar teoretiskt tvätten, men tillför latens och en retention som ADR 0007-resonemanget bör ta ställning till. Vid 500 CV:n per kund och månad är vinsten i absoluta tal liten (cirka 0,45 USD per 500 CV:n i räkneexemplet).

### Analys

**Rekommendation: behåll Sonnet 5.5 som förval. Opus 5.5 är jämförelsemodellen om Sonnet visar sig för grov. Fable 5.2 och Haiku 5.5 är inte förstahandsval.**

- Bedömningen kräver avvägning mellan ansvarsnivå, senioritet och krav i en annons, med fast schema och en motivering som människan läser. Anthropics publicerade kunskapsarbetesiffror (GDPval-AA 1844 mot 1846, AA-Briefcase 1811-1824 mot 1822) visar Sonnet 5.5 och Opus 5.5 nära varandra till hälften av priset, medan Haiku 5.5 ligger märkbart lägre (1620, 1578). Det är generell kunskapsarbetsprestanda, inte CV-matchning.
- Anthropic säger själva att Opus är bättre på "complex, open-ended work requiring sustained judgment". Det beskriver inte en kort strukturerad bedömning av ett enskilt CV. Skillnaden är därför en hypotes som måste mätas på Equas data.
- Haiku 5.5 vore ungefär tjugo gånger billigare (räkneexemplet) men saknar sannolikt marginalen för att särskilja mellan 51-75 och 76-90 på ansvarsnivå. Det är en gissning som #12:s jämförelse kan bekräfta eller förkasta.
- Fable 5.2: dubbla Opus-priset, 30 dagars retention som krav, och Anthropic placerar den för långkörande agentarbete. Inget talar för den här uppgiften.
- Poängen är ett beslutsstöd som människan alltid granskar (ADR 0003). Det minskar värdet av att betala för det sista kvalitetssteget, men höjer kravet på att poängen är konsekvent mellan CV:n i samma analys.

### Jämförelse i korthet

| | Tvätt | Analys |
|---|---|---|
| Haiku 5.5 | Förval | Troligen för svag, mät |
| Sonnet 5.5 | Jämförelse om Haiku missar | Förval |
| Opus 5.5 | Ej motiverad | Jämförelse om Sonnet är för grov |
| Fable 5.2 | Ej motiverad, 30 dagars retention | Ej motiverad, 30 dagars retention |

## 7. Osäkert och bara avgörbart genom test på Equas data

1. **Tvättens recall:** hur ofta missar Haiku 5.5 (och Sonnet 5.5) ett namn, en adress, en ålder eller ett könspronomen på riktiga svenska CV:n, och hur ofta ändras sakinnehåll? Kräver manuell granskning av ett stickprov. Ingen publicerad benchmark mäter detta.
2. **Analysens kvalitet och konsistens:** rangordning och poäng för Haiku, Sonnet och Opus på samma CV:n och annonser, mot ägarens egen bedömning och pilotens utfall. Mät även spridning vid upprepade körningar (samplingparametrar går inte att styra).
3. **Tänkandets påverkan:** faktisk förbrukning av thinking-tokens, `stop_reason: "max_tokens"`-frekvens, latens och kostnad vid `effort` `low`, `medium`, `high`, och med tänkande avstängt, för båda stegen. Se observation 1 i avsnitt 5.
4. **Tokenräkning på svenska:** tokenizern ger "approximately 30 % more tokens" än den äldre, men hur svenska CV:n räknas är ej verifierat. Siffrorna i räkneexemplet är antaganden.
5. **Refusal-frekvens:** hur ofta Haiku 5.5:s och Sonnet 5.5:s klassificerare avvisar vanliga CV:n (till exempel CV:n från säkerhets-, bio- eller läkemedelsbranschen).
6. **Absolut latens och genomströmning:** Anthropic publicerar bara en relativ skala. Mät end-to-end per CV med `max_parallel_cvs=7`, och hastighetsgränser (rate limits) för kontots tier hämtades inte.
7. **Retention och region:** Standardretention utan ZDR-avtal och eventuell EU-inferens är ej verifierade. Mot bakgrund av att `inference_geo` bara har `global` och `us` bör detta hanteras i DPA-arbetet (ADR 0007), inte av modellvalet.
8. **Andra leverantörer:** ingen kvalitetsjämförelse mot GPT-6 Luna/Sol eller Gemini har gjorts med primärkälla.

## 8. Beslut som kräver användaren

1. Ska **Batch API** användas för tvätt eller analys? Det halverar priset men innebär 29 dagars lagring hos Anthropic utan ZDR, och latens upp till 24 timmar (oftast under en timme). Förutsätter ställningstagande i DPA och ADR 0007.
2. Är ett **leverantörsbyte** (OpenAI, Google) överhuvudtaget aktuellt, givet Anthropic som enda underbiträde i ADR 0007? Annars behöver det inte utredas vidare.
3. Vilket **kvalitetskriterium** låser #12 modellvalet mot (till exempel högsta tillåtna andel missade identifierare i tvätt, och minsta överensstämmelse med ägarens bedömning i analys)? Utan ett uttalat kriterium går valet inte att avgöra objektivt.

## Källor

Alla hämtade 2026-11-13.

- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/pricing
- https://platform.claude.com/docs/en/about-claude/models/choosing-a-model
- https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence (första 100 000 tecknen av ca 216 000 lästes)
- https://platform.claude.com/docs/en/models/haiku-5-5/overview
- https://platform.claude.com/docs/en/models/haiku-5-5/whats-new-haiku-5-5
- https://platform.claude.com/docs/en/models/sonnet-5-5/overview
- https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5
- https://platform.claude.com/docs/en/models/opus-5-5/overview
- https://platform.claude.com/docs/en/models/fable-5-2/overview
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5
- https://platform.claude.com/docs/en/build-with-claude/effort
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs (första 100 000 av ca 115 000 tecken lästes)
- https://platform.claude.com/docs/en/build-with-claude/batch-processing
- https://platform.claude.com/docs/en/build-with-claude/fast-mode
- https://platform.claude.com/docs/en/manage-claude/api-and-data-retention
- https://platform.claude.com/docs/en/manage-claude/data-residency
- https://www.anthropic.com/claude-haiku-5-5
- https://www.anthropic.com/claude-sonnet-5-5
- https://www.anthropic.com/claude-fable-and-mythos-5-2
- https://developers.openai.com/api/docs/pricing
- Repot: `GLOSSARY.md`, `docs/adr/0002`, `0003`, `0005`, `0007`, `backend/src/equa_backend/config.py`, `backend/src/equa_backend/pipeline.py`, `docs/reference/pilot.py`, GitHub-issue #12.

Notering om metod: sidorna hämtades via WebFetch, som sammanfattar sidan med en liten modell innan jag ser den. Siffror som är kritiska för beslutet (priser, batch, effort-regler) bör kontrolleras mot Anthropics prissida innan de läggs in i avtal eller budget.
