"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { getMe, type Me } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { Analyses } from "./analyses";

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  if (!ready) return null;
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-semibold">Equa</h1>
      {session ? <Profile email={session.user.email ?? ""} /> : <Login />}
    </main>
  );
}

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setError("Fel e-post eller lösenord.");
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <p className="text-sm text-zinc-600">Logga in. Equa är bara öppet för inbjudna kunder.</p>
      <input
        type="email"
        required
        placeholder="E-post"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="rounded border border-zinc-300 p-2"
      />
      <input
        type="password"
        required
        placeholder="Lösenord"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="rounded border border-zinc-300 p-2"
      />
      <button className="rounded bg-black p-2 text-white">Logga in</button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}

function Profile({ email }: { email: string }) {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <section className="flex flex-col gap-3">
      <p className="text-sm text-zinc-600">Inloggad som {email}</p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {me && (
        <div className="rounded border border-zinc-300 p-4">
          <p className="font-medium">
            Månadskvot: {me.quota.used} av {me.quota.limit} CV:n använda
          </p>
          <p className="text-sm text-zinc-600">
            Raderingstid: {me.default_retention_days} dagar som standard, högst{" "}
            {me.max_retention_days} dagar. Största fil: {me.max_file_size_mb} MB.
          </p>
        </div>
      )}
      {me && <Analyses me={me} />}
      <button onClick={() => supabase.auth.signOut()} className="self-start text-sm underline">
        Logga ut
      </button>
    </section>
  );
}
