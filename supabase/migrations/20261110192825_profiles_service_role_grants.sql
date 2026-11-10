-- Projektet är satt till att inte exponera nya tabeller automatiskt, så ingen
-- roll får rättigheter av sig själv. Backend (service_role) är den enda som
-- ska nå tabellen (ADR 0002) och får därför uttryckligen rättigheter här.
-- anon och authenticated har fortsatt inga rättigheter.
grant select, insert, update, delete on public.profiles to service_role;
