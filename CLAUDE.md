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
