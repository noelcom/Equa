import type { Me } from "@/lib/api";

// Texten speglar faktisk lagring (ADR 0007): bara bedömning och originalfil sparas,
// och raderingstiden kommer från profilen så siffrorna alltid stämmer.
export function DataHandling({ me }: { me: Me }) {
  return (
    <details className="rounded border border-zinc-300 p-4 text-sm">
      <summary className="cursor-pointer font-medium">Så hanteras din data</summary>
      <div className="mt-3 flex flex-col gap-2 text-zinc-700">
        <p>
          <strong>Vad vi sparar.</strong> Bara bedömningen av varje kandidat och den uppladdade
          originalfilen (krypterad). Den anonymiserade texten som skickas till AI-tjänsten sparas
          aldrig.
        </p>
        <p>
          <strong>Hur länge.</strong> Analysen och originalfilerna raderas automatiskt vid
          raderingsdatumet. Standard är {me.default_retention_days} dagar och du kan välja ett eget
          datum, högst {me.max_retention_days} dagar fram. Du kan förlänga i efterhand, men bara
          genom ett aktivt val. Raderingen kan inte stängas av och du kan även radera direkt.
        </p>
        <p>
          <strong>Maskeringen är inte ofelbar.</strong> Namn, kontaktuppgifter och liknande tas
          bort automatiskt, men något kan missas. Betrakta därför inte en kandidat som helt
          anonym.
        </p>
        <p>
          <strong>Människan beslutar.</strong> Poängen är ett beslutsstöd, aldrig ett avvisande.
          Urvalet görs alltid av en människa, och ingen kandidat filtreras bort automatiskt.
        </p>
      </div>
    </details>
  );
}
