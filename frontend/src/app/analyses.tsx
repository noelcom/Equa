"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createAnalysis,
  getAnalysis,
  listAnalyses,
  runAnalysis,
  type Analysis,
  type AnalysisSummary,
  type Candidate,
  type Me,
  type PipelineStep,
} from "@/lib/api";

const POLL_MS = 2000;
// Backend tar om CV:n som stått som pågående längre än så (stale_cv_minutes, 15 min).
// Först därefter kan en ny körning faktiskt rädda ett fastnat CV.
const STALL_MS = 15 * 60 * 1000 + 30_000;

const STEP_LABEL: Record<PipelineStep, string> = {
  pre_wash: "Förtvättar",
  ai_wash: "Anonymiserar",
  safety_check: "Säkerhetskontroll",
  assessment: "Bedömer",
};

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

  // Medan en körning pågår hämtas analysen om och om igen, så att progress och
  // leaderboard uppdateras i realtid.
  const runningId = selected?.state === "running" ? selected.id : null;
  useEffect(() => {
    if (!runningId) return;
    const timer = setInterval(() => {
      getAnalysis(runningId)
        .then(setSelected)
        .catch((e: Error) => setError(e.message));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runningId]);

  async function startRun(id: string) {
    setError(null);
    try {
      setSelected(await runAnalysis(id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      {error && <p className="text-sm text-red-600">{error}</p>}
      {selected ? (
        <AnalysisView
          analysis={selected}
          onBack={() => void open(null)}
          onRun={() => void startRun(selected.id)}
        />
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

function AnalysisView({
  analysis,
  onBack,
  onRun,
}: {
  analysis: Analysis;
  onBack: () => void;
  onRun: () => void;
}) {
  const ranked = analysis.candidates.filter((c) => c.status === "done");
  const waiting = analysis.candidates.filter(
    (c) => c.status === "uploaded" || c.status === "queued" || c.status === "processing",
  );
  const failed = analysis.candidates.filter((c) => c.status === "failed");
  const { total, finished } = analysis.progress;

  // Om ingen framgång syns på länge antas en körning ha fastnat, och användaren kan ta om den.
  // Nyckeln byts när framgången ändras, så ett gammalt "fastnat" försvinner av sig självt.
  const [stalledKey, setStalledKey] = useState<string | null>(null);
  const running = analysis.state === "running";
  const progressKey = `${analysis.id}:${finished}`;
  useEffect(() => {
    if (!running) return;
    const timer = setTimeout(() => setStalledKey(progressKey), STALL_MS);
    return () => clearTimeout(timer);
  }, [running, progressKey]);
  const stalled = running && stalledKey === progressKey;

  return (
    <div className="flex flex-col gap-3">
      <button onClick={onBack} className="self-start text-sm underline">
        Tillbaka
      </button>
      <h2 className="text-xl font-semibold">{analysis.title}</h2>
      <p className="text-sm text-zinc-600">Raderas {formatDate(analysis.expires_at)}</p>

      {analysis.state === "ready" && (
        <button onClick={onRun} className="self-start rounded bg-black px-4 py-2 text-white">
          Starta analys
        </button>
      )}
      {analysis.state === "running" && (
        <div className="flex flex-col gap-1" role="status">
          <p className="text-sm">
            Analyserar… {finished} av {total} CV:n klara
          </p>
          <progress value={finished} max={total} className="w-full" />
          {stalled && (
            <div className="flex flex-col gap-1">
              <p className="text-sm text-zinc-600">
                Det verkar ha hakat upp sig. Du kan ta om de CV:n som inte blev klara.
              </p>
              <button onClick={onRun} className="self-start rounded bg-black px-4 py-2 text-white">
                Ta om fastnade CV:n
              </button>
            </div>
          )}
        </div>
      )}

      {ranked.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-medium">Leaderboard</h3>
          <p className="text-xs text-zinc-600">
            Poängen är ett beslutsstöd. Urvalet gör alltid du.
          </p>
          <ol className="flex flex-col gap-2">
            {ranked.map((c, i) => (
              <RankedCandidate key={c.alias} candidate={c} rank={i + 1} />
            ))}
          </ol>
        </div>
      )}

      {waiting.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-medium">{analysis.state === "ready" ? "Uppladdade" : "Pågår"}</h3>
          <ul className="flex flex-col gap-1">
            {waiting.map((c) => (
              <li key={c.alias} className="rounded border border-zinc-300 p-2 text-sm">
                {c.alias}
                {c.step && <span className="text-zinc-600"> · {STEP_LABEL[c.step]}</span>}
                {c.status === "queued" && <span className="text-zinc-600"> · I kö</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failed.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-medium">Kunde inte analyseras</h3>
          <ul className="flex flex-col gap-1">
            {failed.map((c) => (
              <li key={c.alias} className="rounded border border-zinc-300 p-2 text-sm">
                {c.alias}
                <span className="block text-zinc-600">{c.failure_reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RankedCandidate({ candidate, rank }: { candidate: Candidate; rank: number }) {
  const a = candidate.assessment;
  if (!a) return null;
  return (
    <li className="rounded border border-zinc-300 p-3">
      <details>
        <summary className="flex cursor-pointer items-baseline justify-between gap-3">
          <span>
            <span className="text-zinc-600">{rank}.</span> {candidate.alias}
          </span>
          <span className="font-medium">{a.score} / 100</span>
        </summary>
        <dl className="mt-3 flex flex-col gap-2 text-sm">
          <Detail label="Relevanta år i branschen">{a.years_experience}</Detail>
          <Detail label="Utbildning">{a.education_match}</Detail>
          <Detail label="Konkreta resultat">{a.concrete_results}</Detail>
          <Detail label="Nyckelkompetenser">{a.key_skills.join(", ")}</Detail>
          <Detail label="Saknade krav">{a.missing_requirements}</Detail>
          <Detail label="Motivering">{a.rationale}</Detail>
        </dl>
      </details>
    </li>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="font-medium">{label}</dt>
      <dd className="text-zinc-700">{children}</dd>
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("sv-SE");
}
