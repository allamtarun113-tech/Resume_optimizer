"use client";

import { useEffect, useState } from "react";
import { CheckIcon, Loader2Icon } from "lucide-react";
import { cn } from "cn";
import type { AnalysisStatus } from "@/lib/types";

// Every step from clicking Analyze to results. "uploading" happens in the browser
// (/analysis/new); the rest are the backend's analysis statuses.
export type ProgressStage = "uploading" | AnalysisStatus;

const STAGES: { stage: ProgressStage; label: string }[] = [
  { stage: "uploading", label: "Uploading your documents" },
  { stage: "parsing", label: "Reading your documents" },
  { stage: "extracting", label: "Understanding your profile and the job" },
  { stage: "scoring", label: "Matching and scoring" },
  { stage: "advising", label: "Writing suggestions and your learning path" },
];

export function stageIndex(stage: ProgressStage): number {
  if (stage === "queued") return 1;
  if (stage === "done") return STAGES.length;
  return Math.max(
    0,
    STAGES.findIndex((s) => s.stage === stage),
  );
}

const SLOW_AFTER_MS = 12_000;

export function AnalysisProgress({ stage }: { stage: ProgressStage }) {
  const current = stageIndex(stage);

  return (
    <div
      className="mx-auto flex w-full max-w-xl flex-col gap-6 rounded-2xl border bg-card p-8 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-col items-center gap-2 text-center">
        <Loader2Icon className="size-8 animate-spin text-primary" />
        <h1 className="text-xl font-semibold">Analyzing your fit…</h1>
        <p className="text-sm text-muted-foreground">
          Usually under a minute. Keep this page open; results appear here.
        </p>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="bg-brand-gradient h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.max(6, (current / STAGES.length) * 100)}%` }}
        />
      </div>
      <ol className="flex flex-col gap-3">
        {STAGES.map((s, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={s.stage} className="flex items-center gap-3 text-sm">
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs",
                  done && "border-primary bg-primary text-primary-foreground",
                  active && "border-primary text-primary",
                )}
              >
                {done ? (
                  <CheckIcon className="size-3.5" />
                ) : active ? (
                  <Loader2Icon className="size-3.5 animate-spin" />
                ) : (
                  i + 1
                )}
              </span>
              <span className={cn(!done && !active && "text-muted-foreground")}>
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>
      {/* Keyed by step, so the timer restarts whenever progress moves on. */}
      <SlowHint key={current} uploading={current === 0} />
    </div>
  );
}

// If a step takes long (e.g. the free server waking up), say so.
function SlowHint({ uploading }: { uploading: boolean }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, []);
  if (!slow) return null;
  return (
    <p className="rounded-lg bg-muted/60 px-4 py-3 text-center text-xs text-muted-foreground">
      {uploading
        ? "Still uploading. If the app hasn't been used for a while, the server takes up to a minute to wake up."
        : "This step is taking a little longer than usual; it's still working."}
    </p>
  );
}
