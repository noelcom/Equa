## Agent skills

### Issue tracker

Issues live in GitHub Issues for noelcom/Equa (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Kommandon

Starta, testa och linta: `backend/README.md`. Frontend: `npm run check` i `frontend/`.

## Vägen till main

En ändring som går att backa committas på `main` och pushas direkt. En ändring som inte går att ångra går via gren och PR som användaren mergar själv: den raderar data eller filer, ändrar raderingsjobbet eller migrerar databasen. Osäker? Ta PR-vägen.

## Restpunkter efter ett issue

Sortera det som blev över (granskningsfynd, "gick inte", "bör ses över") innan du rapporterar till användaren:

1. **Litet och inom issuet:** fixa det före commit.
2. **Tydligt men eget jobb:** skriv ett issue med `ready-for-agent`.
3. **Kräver ett beslut av användaren:** lista det med frågan som behöver svar. Det tas till `/grill-with-docs`.
4. **Inte värt det:** nämn det på en rad och släpp det.

Det som gick inte att göra får också en orsak: ett saknat beslut (3), något trasigt (`/diagnosing-bugs`) eller större än väntat (2). Rapporten slutar med hög 3 som det enda användaren behöver ta ställning till.
