import { supabase } from "./supabase";

export type Me = {
  quota: { limit: number; used: number };
  default_retention_days: number;
  max_retention_days: number;
  max_file_size_mb: number;
};

export type Analysis = {
  id: string;
  title: string;
  job_ad: string;
  expires_at: string;
  created_at: string;
  candidates: { alias: string }[];
};

export type AnalysisSummary = {
  id: string;
  title: string;
  expires_at: string;
  created_at: string;
  candidate_count: number;
};

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Svaret var inte JSON, använd standardmeddelandet.
  }
  return `${fallback} (${res.status}).`;
}

export async function getMe(): Promise<Me> {
  const res = await authedFetch("/me");
  if (!res.ok) throw new Error(`Kunde inte hämta profilen (${res.status}).`);
  return res.json();
}

export async function listAnalyses(): Promise<AnalysisSummary[]> {
  const res = await authedFetch("/analyses");
  if (!res.ok) throw new Error(await errorMessage(res, "Kunde inte hämta analyserna"));
  return res.json();
}

export async function getAnalysis(id: string): Promise<Analysis> {
  const res = await authedFetch(`/analyses/${id}`);
  if (!res.ok) throw new Error(await errorMessage(res, "Kunde inte hämta analysen"));
  return res.json();
}

export async function createAnalysis(
  title: string,
  jobAd: string,
  files: File[],
): Promise<Analysis> {
  const form = new FormData();
  form.append("title", title);
  form.append("job_ad", jobAd);
  for (const f of files) form.append("files", f);
  const res = await authedFetch("/analyses", { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorMessage(res, "Kunde inte skapa analysen"));
  return res.json();
}
