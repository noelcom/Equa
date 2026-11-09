# 0002 – All logik ligger i backend

Status: accepterad

## Beslut
Frontend anropar bara backend-API:et (inloggning går via Supabase Auth). Kvot, radering, anonymisering och bedömning ligger i FastAPI. Frontend pratar aldrig direkt med AI eller med kandidatdata.

## Varför
Designen kan ändras fritt utan att röra reglerna, och säkerhetskritisk logik finns på ett ställe.

## Konsekvenser
Frontend hålls tunn. Nya regler läggs i backend.
