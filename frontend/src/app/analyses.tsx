"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createAnalysis,
  getAnalysis,
  listAnalyses,
  type Analysis,
  type AnalysisSummary,
  type Me,
} from "@/lib/api";

const SELECTED_KEY = "equa.selectedAnalysis";

function readSelected(): string | null {
  try {
    return sessionStorage.getItem(SELECTED_KEY);
  } catch {
    return null;
  }
}

function writeSelected(id: string | null) {
  try {
    if (id) sessionStorage.setItem(SELECTED_KEY, id);
    else sessionStorage.removeItem(SELECTED_KEY);
  } catch {
    // Utan lagring väljs ingen analys om efter uppdatering, men listan finns kvar.
  }
}

export function Analyses({ me }: { me: Me }) {
  const [list, setList] = useState<AnalysisSummary[]>([]);
  const [selected, setSelected] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = useCallback(async (id: string | null) => {
    setError(null);
    if (!id) {
      setSelected(null);
      writeSelected(null);
      return;
    }
    try {
      setSelected(await getAnalysis(id));
      writeSelected(id);
    } catch (e) {
      setError((e as Error).message);
      writeSelected(null);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      setList(await listAnalyses());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    // Ladda listan och den senast öppnade analysen så att sidan överlever uppdatering.
    listAnalyses()
      .then(setList)
      .catch((e: Error) => setError(e.message));
    const id = readSelected();
    if (id) {
      getAnalysis(id)
        .then(setSelected)
        .catch((e: Error) => {
          setError(e.message);
          writeSelected(null);
        });
    }
  }, []);

  return (
    <section className="flex flex-col gap-4">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {selected ? (
        <AnalysisView analysis={selected} onBack={() => void open(null)} />
      ) : (
        <>
          <NewAnalysis
            me={me}
            onCreated={async (a) => {
              await refresh();
              setSelected(a);
              writeSelected(a.id);
            }}
          />
          <AnalysisList list={list} onOpen={(id) => void open(id)} />
        </>
      )}
    </section>
  );
}

function NewAnalysis({ me, onCreated }: { me: Me; onCreated: (a: Analysis) => void }) {
  const [title, setTitle] = useState("");
  const [jobAd, setJobAd] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // Snabb kontroll i webbläsaren. Backend gör den skarpa kontrollen.
    const tooBig = files.findIndex((f) => f.size > me.max_file_size_mb * 1024 * 1024);
    if (tooBig >= 0) {
      setError(
        `Kandidat #${tooBig + 1} är större än den tillåtna filstorleken på ${me.max_file_size_mb} MB.`,
      );
      return;
    }
    setBusy(true);
    try {
      onCreated(await createAnalysis(title, jobAd, files));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 rounded border border-zinc-300 p-4">
      <h2 className="font-medium">Ny analys</h2>
      <input
        required
        placeholder="Titel"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="rounded border border-zinc-300 p-2"
      />
      <textarea
        required
        rows={6}
        placeholder="Klistra in arbetsannonsen"
        value={jobAd}
        onChange={(e) => setJobAd(e.target.value)}
        className="rounded border border-zinc-300 p-2"
      />
      <label className="flex flex-col gap-1 text-sm">
        CV:n som PDF (högst {me.max_file_size_mb} MB per fil)
        <input
          type="file"
          accept="application/pdf"
          multiple
          required
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </label>
      <p className="text-xs text-zinc-600">
        Originalfilerna raderas automatiskt efter {me.default_retention_days} dagar.
      </p>
      <button disabled={busy} className="rounded bg-black p-2 text-white disabled:opacity-50">
        {busy ? "Laddar upp…" : "Skapa analys"}
      </button>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </form>
  );
}

function AnalysisList({
  list,
  onOpen,
}: {
  list: AnalysisSummary[];
  onOpen: (id: string) => void;
}) {
  if (list.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <h2 className="font-medium">Dina analyser</h2>
      <ul className="flex flex-col gap-2">
        {list.map((a) => (
          <li key={a.id}>
            <button
              onClick={() => onOpen(a.id)}
              className="w-full rounded border border-zinc-300 p-3 text-left"
            >
              <span className="font-medium">{a.title}</span>
              <span className="block text-sm text-zinc-600">
                {a.candidate_count} kandidater · raderas {formatDate(a.expires_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AnalysisView({ analysis, onBack }: { analysis: Analysis; onBack: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <button onClick={onBack} className="self-start text-sm underline">
        Tillbaka
      </button>
      <h2 className="text-xl font-semibold">{analysis.title}</h2>
      <p className="text-sm text-zinc-600">Raderas {formatDate(analysis.expires_at)}</p>
      <ul className="flex flex-col gap-1">
        {analysis.candidates.map((c) => (
          <li key={c.alias} className="rounded border border-zinc-300 p-2">
            {c.alias}
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("sv-SE");
}
