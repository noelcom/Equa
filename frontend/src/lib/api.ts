import { supabase } from "./supabase";

export type Me = {
  quota: { limit: number; used: number };
  default_retention_days: number;
  max_retention_days: number;
  max_file_size_mb: number;
};

export type Assessment = {
  score: number;
  years_experience: number;
  education_match: string;
  concrete_results: string;
  key_skills: string[];
  missing_requirements: string;
  rationale: string;
};

export type CandidateStatus = "uploaded" | "queued" | "processing" | "done" | "failed";
export type PipelineStep = "pre_wash" | "ai_wash" | "safety_check" | "assessment";

export type Candidate = {
  alias: string;
  status: CandidateStatus;
  step: PipelineStep | null;
  assessment: Assessment | null;
  failure_reason: string | null;
};

export type Analysis = {
  id: string;
  title: string;
  job_ad: string;
  expires_at: string;
  created_at: string;
  // ready: det finns CV:n att köra. running: körning pågår. finished: inget mer att köra.
  state: "ready" | "running" | "finished";
  progress: { total: number; finished: number };
  // Bedömda kandidater efter poäng (högst först), därefter övriga i nummerordning.
  candidates: Candidate[];
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

export async function runAnalysis(id: string): Promise<Analysis> {
  const res = await authedFetch(`/analyses/${id}/run`, { method: "POST" });
  if (!res.ok) throw new Error(await errorMessage(res, "Kunde inte starta analysen"));
  return res.json();
}

// Avslöja: laddar ner originalfilen för en kandidat. Loggas inte (ADR 0004).
export async function revealCandidate(analysisId: string, alias: string): Promise<void> {
  const number = alias.replace("Kandidat #", "");
  const res = await authedFetch(`/analyses/${analysisId}/candidates/${number}/original`);
  if (!res.ok) throw new Error(await errorMessage(res, "Kunde inte avslöja kandidaten"));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `Kandidat-${number}.pdf`;
  a.click();
  // Vänta lite så webbläsaren hinner starta nedladdningen innan URL:en släpps.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
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
