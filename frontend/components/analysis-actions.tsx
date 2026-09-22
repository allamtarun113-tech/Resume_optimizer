"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { apiDownload, apiPostJson } from "@/lib/api";
import { MAX_JD_CHARS, MIN_JD_CHARS } from "@/lib/analyze";
import type { AnalysisCreated, AnalysisRerun } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
        {downloading ? "Preparing…" : "Download report (.md)"}
      </Button>
      <Button variant="outline" size="sm" onClick={() => window.print()}>
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
        `Paste the full job description (at least ${MIN_JD_CHARS} characters).`,
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
      toast.error((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <Card className="print:hidden">
      <CardHeader>
        <CardTitle>Try another job</CardTitle>
        <CardDescription>
          Check the same resume and documents against a different job
          description. Your profile is reused, so it&apos;s quicker.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Label htmlFor="rerun-jd" className="sr-only">
            Job description
          </Label>
          <Textarea
            id="rerun-jd"
            rows={6}
            maxLength={MAX_JD_CHARS}
            placeholder="Paste another job description."
            value={jdText}
            disabled={busy}
            onChange={(e) => setJdText(e.target.value)}
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
