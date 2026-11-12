"use client";

import { useCallback, useEffect, useState } from "react";
import {
  addCandidates,
  createAnalysis,
  deleteAnalysis,
  extendAnalysis,
  getAnalysis,
  listAnalyses,
  revealCandidate,
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

export function Analyses({ me, onMeChanged }: { me: Me; onMeChanged: () => void }) {
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
        .then((a) => {
          setSelected(a);
          // Körningen är klar: kvoten har ändrats.
          if (a.state !== "running") onMeChanged();
        })
        .catch((e: Error) => setError(e.message));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runningId, onMeChanged]);

  async function extend(id: string, date: Date) {
    setError(null);
    try {
      setSelected(await extendAnalysis(id, date));
      void refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await deleteAnalysis(id);
      await open(null);
      await refresh();
      onMeChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function startRun(id: string) {
    setError(null);
    try {
      setSelected(await runAnalysis(id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      onMeChanged();
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
          onAdded={(a) => {
            setSelected(a);
            void refresh();
            onMeChanged();
          }}
          remaining={me.quota.remaining}
          maxFileSizeMb={me.max_file_size_mb}
          maxRetentionDays={me.max_retention_days}
          onExtend={(d) => void extend(selected.id, d)}
          onDelete={() => void remove(selected.id)}
        />
      ) : (
        <>
          <NewAnalysis
            me={me}
            onCreated={async (a) => {
              await refresh();
              onMeChanged();
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
  const [retention, setRetention] = useState<string>("default");
  const [customDate, setCustomDate] = useState("");
  const [mountedAt] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const overQuota = files.length > me.quota.remaining;

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
    let expiresAt: Date | null = null;
    if (retention === "custom") {
      expiresAt = endOfDay(customDate);
    } else if (retention !== "default") {
      expiresAt = new Date(Date.now() + Number(retention) * 3600 * 1000);
    }
    setBusy(true);
    try {
      onCreated(await createAnalysis(title, jobAd, files, expiresAt));
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
      {overQuota && <QuotaNotice max={me.quota.remaining} />}
      <label className="flex flex-col gap-1 text-sm">
        Raderingsdatum
        <select
          value={retention}
          onChange={(e) => setRetention(e.target.value)}
          className="rounded border border-zinc-300 p-2"
        >
          <option value="24">24 timmar</option>
          <option value="default">{me.default_retention_days} dagar (förval)</option>
          <option value="336">14 dagar</option>
          <option value="custom">Eget datum</option>
        </select>
      </label>
      {retention === "custom" && (
        <input
          type="date"
          required
          value={customDate}
          min={dateInput(new Date(mountedAt + 24 * 3600 * 1000))}
          max={dateInput(new Date(mountedAt + (me.max_retention_days - 1) * 24 * 3600 * 1000))}
          onChange={(e) => setCustomDate(e.target.value)}
          className="rounded border border-zinc-300 p-2"
        />
      )}
      <p className="text-xs text-zinc-600">
        Analysen och originalfilerna raderas automatiskt vid raderingsdatumet. Längsta tillåtna
        tid är {me.max_retention_days} dagar. Raderingen kan inte stängas av.
      </p>
      <button
        disabled={busy || overQuota}
        className="rounded bg-black p-2 text-white disabled:opacity-50"
      >
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
  onAdded,
  remaining,
  maxFileSizeMb,
  maxRetentionDays,
  onExtend,
  onDelete,
}: {
  analysis: Analysis;
  onBack: () => void;
  onRun: () => void;
  onAdded: (a: Analysis) => void;
  remaining: number;
  maxFileSizeMb: number;
  maxRetentionDays: number;
  onExtend: (date: Date) => void;
  onDelete: () => void;
}) {
  const [newDate, setNewDate] = useState("");
  // Rullande tak: det räknas från idag, inte från skapandet (ADR 0007).
  const latest = new Date(Date.now() + maxRetentionDays * 86400_000);
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
  // Samma regel som backend: körningen nekas om den har fler CV:n än kvoten räcker till.
  const runBlocked = analysis.runnable_count > remaining;
  const runBlockedNotice = runBlocked && (
    <p className="text-sm text-zinc-600">
      Analysen har {analysis.runnable_count} CV:n att köra men du har {remaining} kvar den här
      månaden. Kvoten fylls på den {nextMonthStart()}.
    </p>
  );

  return (
    <div className="flex flex-col gap-3">
      <button onClick={onBack} className="self-start text-sm underline">
        Tillbaka
      </button>
      <h2 className="text-xl font-semibold">{analysis.title}</h2>
      <p className="text-sm text-zinc-600">
        Raderas {formatDate(analysis.expires_at)} (längst {formatDate(latest.toISOString())})
      </p>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <input
          type="date"
          value={newDate}
          min={dateInput(new Date(analysis.expires_at))}
          max={dateInput(new Date(latest.getTime() - 86400_000))}
          onChange={(e) => setNewDate(e.target.value)}
          className="rounded border border-zinc-300 p-1"
        />
        <button
          disabled={!newDate}
          onClick={() => onExtend(endOfDay(newDate))}
          className="rounded border border-zinc-300 px-3 py-1 disabled:opacity-50"
        >
          Flytta fram raderingsdatum
        </button>
        <button
          onClick={() => {
            if (confirm("Radera analysen, kandidaterna och originalfilerna nu? Det går inte att ångra."))
              onDelete();
          }}
          className="rounded border border-red-600 px-3 py-1 text-red-600"
        >
          Radera direkt
        </button>
      </div>

      <AddCvs
        analysisId={analysis.id}
        // Analysens ej körda CV:n räknas med, så det som laddas upp också går att köra.
        max={Math.max(remaining - analysis.runnable_count, 0)}
        maxFileSizeMb={maxFileSizeMb}
        onAdded={onAdded}
      />

      {analysis.state === "ready" && (
        <div className="flex flex-col gap-1">
          <button
            onClick={onRun}
            disabled={runBlocked}
            className="self-start rounded bg-black px-4 py-2 text-white disabled:opacity-50"
          >
            Starta analys
          </button>
          {runBlockedNotice}
        </div>
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
              <button
                onClick={onRun}
                disabled={runBlocked}
                className="self-start rounded bg-black px-4 py-2 text-white disabled:opacity-50"
              >
                Ta om fastnade CV:n
              </button>
              {runBlockedNotice}
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
              <RankedCandidate key={c.alias} analysisId={analysis.id} candidate={c} rank={i + 1} />
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

// Fler CV:n till samma analys. De bedöms mot samma annons när analysen startas igen,
// och raderingsdatumet ändras inte.
function AddCvs({
  analysisId,
  max,
  maxFileSizeMb,
  onAdded,
}: {
  analysisId: string;
  // Så många CV:n till ryms i kvoten.
  max: number;
  maxFileSizeMb: number;
  onAdded: (a: Analysis) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  // Byts efter en lyckad uppladdning så att filväljaren töms.
  const [inputKey, setInputKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const overQuota = files.length > max;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // Snabb kontroll i webbläsaren. Backend gör den skarpa kontrollen.
    if (files.some((f) => f.size > maxFileSizeMb * 1024 * 1024)) {
      setError(`Ett CV är större än den tillåtna filstorleken på ${maxFileSizeMb} MB.`);
      return;
    }
    setBusy(true);
    try {
      onAdded(await addCandidates(analysisId, files));
      setFiles([]);
      setInputKey((k) => k + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-2 text-sm">
      <label className="flex flex-col gap-1">
        Lägg till fler CV:n som PDF (högst {maxFileSizeMb} MB per fil)
        <input
          key={inputKey}
          type="file"
          accept="application/pdf"
          multiple
          required
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
      </label>
      {overQuota && <QuotaNotice max={max} />}
      <button
        disabled={busy || files.length === 0 || overQuota}
        className="self-start rounded border border-zinc-300 px-3 py-1 disabled:opacity-50"
      >
        {busy ? "Laddar upp…" : "Lägg till CV:n"}
      </button>
      {error && <p className="text-red-600">{error}</p>}
    </form>
  );
}

function RankedCandidate({
  analysisId,
  candidate,
  rank,
}: {
  analysisId: string;
  candidate: Candidate;
  rank: number;
}) {
  const a = candidate.assessment;
  const [error, setError] = useState<string | null>(null);
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
        <button
          onClick={() => {
            setError(null);
            revealCandidate(analysisId, candidate.number).catch((e: Error) => setError(e.message));
          }}
          className="mt-3 rounded border border-zinc-300 px-3 py-1 text-sm"
        >
          Avslöja (ladda ner originalfil)
        </button>
        {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
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

// Neutral notis (inte ett fel): rekryteraren har valt fler filer än kvoten räcker till.
function QuotaNotice({ max }: { max: number }) {
  return (
    <p className="text-sm text-zinc-600" role="status">
      Du kan ladda upp högst {max} CV:n till.
    </p>
  );
}

// "1 december": när kvoten fylls på. Kvoten räknas per kalendermånad i UTC.
function nextMonthStart(): string {
  const now = new Date();
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  return `1 ${next.toLocaleDateString("sv-SE", { month: "long", timeZone: "UTC" })}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("sv-SE");
}

// Lokal datumsträng (ÅÅÅÅ-MM-DD) för <input type="date">.
function dateInput(d: Date): string {
  return d.toLocaleDateString("sv-SE");
}

// Slutet av vald dag (lokal tid), så "eget datum" betyder att analysen finns kvar hela dagen.
function endOfDay(date: string): Date {
  return new Date(`${date}T23:59:59`);
}
