// "1 december": datumet kommer från backend, som äger månadsgränsen (UTC).
export function formatResetDate(iso: string): string {
  return new Date(iso).toLocaleDateString("sv-SE", { day: "numeric", month: "long", timeZone: "UTC" });
}
