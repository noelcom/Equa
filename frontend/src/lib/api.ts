import { supabase } from "./supabase";

export type Me = {
  quota: { limit: number; used: number };
  default_retention_days: number;
  max_retention_days: number;
  max_file_size_mb: number;
};

async function authedFetch(path: string): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export async function getMe(): Promise<Me> {
  const res = await authedFetch("/me");
  if (!res.ok) throw new Error(`Kunde inte hämta profilen (${res.status}).`);
  return res.json();
}
