"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { DownloadIcon, PrinterIcon, RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";
import { apiDownload, apiPostJson } from "@/lib/api";
import { MIN_JD_CHARS } from "@/lib/analyze";
import { showApiError } from "@/lib/errors";
import type { AnalysisCreated, AnalysisRerun } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { JobDescriptionInput } from "@/components/inputs/job-description-input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Export buttons for a finished analysis (hidden when printing).
export function ExportButtons({ analysisId }: { analysisId: string }) {
  const [downloading, setDownloading] = useState(false);

  async function download() {
    setDownloading(true);
    try {
      await apiDownload(
        `/analyses/${analysisId}/export`,
        "resume-optimizer-report.md",
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex flex-wrap gap-2 print:hidden">
      <Button
        variant="outline"
        size="sm"
        onClick={download}
        disabled={downloading}
      >
        <DownloadIcon />
        {downloading ? "Preparing…" : "Download report (.md)"}
      </Button>
      <Button variant="outline" size="sm" onClick={() => window.print()}>
        <PrinterIcon />
        Print / Save as PDF
      </Button>
    </div>
  );
}

// Same resume and documents, a different job description.
export function RerunForm({ analysisId }: { analysisId: string }) {
  const router = useRouter();
  const [jdText, setJdText] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = jdText.trim();
    if (text.length < MIN_JD_CHARS)
      return toast.error(
        `Add the full job description (at least ${MIN_JD_CHARS} characters).`,
      );
    setBusy(true);
    try {
      const body: AnalysisRerun = { jd_text: text };
      const created = await apiPostJson<AnalysisCreated>(
        `/analyses/${analysisId}/rerun`,
        body,
      );
      router.push(`/analysis/${created.id}`);
    } catch (err) {
      showApiError(err, router.push);
      setBusy(false);
    }
  }

  return (
    <Card className="print:hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RefreshCwIcon className="size-4 text-primary" />
          Try another job
        </CardTitle>
        <CardDescription>
          Check the same resume and documents against a different job
          description. Your profile is reused, so it&apos;s quicker.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <JobDescriptionInput
            value={jdText}
            onChange={setJdText}
            disabled={busy}
            rows={6}
            label="Another job description"
          />
          <div>
            <Button type="submit" disabled={busy}>
              {busy ? "Starting…" : "Analyze this job"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
