"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { AnalysisResponse, AnalysisStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RequirementBreakdown } from "@/components/requirement-breakdown";
import { ScoreGauge } from "@/components/score-gauge";
import { GapList, SuggestionList } from "@/components/suggestion-list";
import { LearningPathView } from "@/components/learning-path";
import { InterviewPrep } from "@/components/interview-prep";
import { ExportButtons, RerunForm } from "@/components/analysis-actions";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const POLL_MS = 2000;
const FINAL: AnalysisStatus[] = ["done", "failed"];
const STATUS_TEXT: Record<AnalysisStatus, string> = {
  queued: "Queued",
  parsing: "Reading your documents",
  extracting: "Extracting your profile and the job requirements",
  scoring: "Scoring your fit",
  advising: "Writing suggestions and your learning path",
  done: "Done",
  failed: "Failed",
};

export function AnalysisView({ id }: { id: string }) {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const data = await apiFetch<AnalysisResponse>(`/analyses/${id}`);
        if (cancelled) return;
        setAnalysis(data);
        setError(null);
        if (!FINAL.includes(data.status)) timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (cancelled) return;
        setError((e as Error).message);
        timer = setTimeout(poll, POLL_MS * 2);
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (!analysis) {
    return (
      <p className="text-sm text-muted-foreground">
        {error ? `Could not load analysis: ${error}` : "Loading…"}
      </p>
    );
  }

  const { status, llm_usage: usage } = analysis;
  const profile = analysis.student_profile;
  const requirements = analysis.job_requirements;

  return (
    <div className="flex w-full flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-3">
            {requirements?.role_title ?? "Analysis"}
            <Badge
              variant={
                status === "failed"
                  ? "destructive"
                  : status === "done"
                    ? "default"
                    : "secondary"
              }
            >
              {STATUS_TEXT[status]}
            </Badge>
          </CardTitle>
          <CardDescription>
            {FINAL.includes(status)
              ? `Started ${new Date(analysis.created_at).toLocaleString()}`
              : "This usually takes under a minute. You can leave this page open."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          {analysis.error && (
            <p className="text-destructive">{analysis.error}</p>
          )}
          {analysis.fit_score != null && (
            <div className="flex flex-wrap items-center justify-center gap-10 py-2">
              <ScoreGauge score={analysis.fit_score} label="Job fit (resume)" />
              {analysis.potential_score != null &&
                analysis.potential_score > analysis.fit_score && (
                  <ScoreGauge
                    score={analysis.potential_score}
                    label="With what you already have"
                  />
                )}
            </div>
          )}
          {analysis.fit_score != null && (
            <p className="text-muted-foreground">
              The score weighs each requirement by importance and by how clearly
              your resume shows it. The same resume and job always get the same
              score.
            </p>
          )}
          {status === "done" && <ExportButtons analysisId={analysis.id} />}
        </CardContent>
      </Card>

      {analysis.suggestions && (
        <SuggestionList
          suggestions={analysis.suggestions}
          rejectedCount={analysis.rejected_suggestions?.length ?? 0}
          fitScore={analysis.fit_score}
          potentialScore={analysis.potential_score}
        />
      )}
      {analysis.gaps && <GapList gaps={analysis.gaps} />}
      {analysis.learning_path && (
        <LearningPathView path={analysis.learning_path} />
      )}
      {status === "done" && <InterviewPrep analysisId={analysis.id} />}
      {status === "done" && <RerunForm analysisId={analysis.id} />}
      {status === "failed" && (
        <div className="print:hidden">
          <Button nativeButton={false} render={<Link href="/analyze" />}>
            Start a new analysis
          </Button>
        </div>
      )}

      {analysis.matches && (
        <section className="flex flex-col gap-4">
          <h2 className="text-xl font-semibold tracking-tight">
            Requirement by requirement
          </h2>
          <RequirementBreakdown
            matches={analysis.matches}
            skip={analysis.gaps ? ["true_gap"] : []}
          />
        </section>
      )}

      {(requirements || profile) && (
        <details className="rounded-xl border p-4 text-sm print:hidden">
          <summary className="cursor-pointer text-muted-foreground">
            Raw extraction data
            {usage.calls > 0 &&
              ` · AI calls: ${usage.calls} (${usage.cached_calls} from cache)`}
          </summary>
          <div className="mt-4 flex flex-col gap-4">
            {requirements && (
              <JsonCard title="Job requirements" data={requirements} />
            )}
            {profile && <JsonCard title="Your profile" data={profile} />}
          </div>
        </details>
      )}
    </div>
  );
}

// Debug view of the raw extraction output.
function JsonCard({ title, data }: { title: string; data: unknown }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="font-medium">{title}</h3>
      <pre className="max-h-[32rem] overflow-auto rounded-md bg-muted p-4 text-xs">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
