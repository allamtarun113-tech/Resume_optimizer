"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangleIcon, ArrowLeftIcon, SettingsIcon } from "lucide-react";
import { isNoKeyError } from "@/lib/errors";
import {
  clearPendingAnalysis,
  getPendingAnalysis,
  startPendingAnalysis,
} from "@/lib/pending-analysis";
import { AnalysisProgress } from "@/components/analysis-progress";
import { Button } from "@/components/ui/button";

// Shown right after clicking Analyze: uploads the documents and starts the analysis,
// then swaps to /analysis/<id>, where progress continues until the results are ready.
export function PendingAnalysis() {
  const router = useRouter();
  const [error, setError] = useState<{
    message: string;
    noKey: boolean;
  } | null>(null);

  useEffect(() => {
    const payload = getPendingAnalysis();
    if (!payload) {
      router.replace("/analyze"); // e.g. the page was reloaded
      return;
    }
    let active = true;
    startPendingAnalysis(payload)
      .then((id) => {
        if (!active) return;
        clearPendingAnalysis();
        router.replace(`/analysis/${id}`);
      })
      .catch((e: unknown) => {
        if (active)
          setError({
            message: (e as Error).message || "Something went wrong.",
            noKey: isNoKeyError(e),
          });
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!error) return <AnalysisProgress stage="uploading" />;

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-4 rounded-2xl border bg-card p-8 text-center shadow-sm">
      <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertTriangleIcon className="size-6" />
      </span>
      <h1 className="text-xl font-semibold">
        We couldn&apos;t start the analysis
      </h1>
      <p className="text-muted-foreground">{error.message}</p>
      <div className="flex flex-wrap justify-center gap-3">
        {/* The form keeps everything you entered. */}
        <Button onClick={() => router.push("/analyze")}>
          <ArrowLeftIcon />
          Back to the form
        </Button>
        {error.noKey && (
          <Button variant="outline" onClick={() => router.push("/settings")}>
            <SettingsIcon />
            Open Settings
          </Button>
        )}
      </div>
    </div>
  );
}
