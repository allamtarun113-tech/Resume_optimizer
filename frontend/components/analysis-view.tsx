"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangleIcon,
  BookOpenCheckIcon,
  LayoutListIcon,
  MessagesSquareIcon,
  WandSparklesIcon,
} from "lucide-react";
import { cn } from "cn";
import { apiFetch } from "@/lib/api";
import type { AnalysisResponse, AnalysisStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RequirementBreakdown } from "@/components/requirement-breakdown";
import { ScoreGauge } from "@/components/score-gauge";
import { GapList, SuggestionList } from "@/components/suggestion-list";
import { LearningPathView } from "@/components/learning-path";
import { InterviewPrep } from "@/components/interview-prep";
import { ExportButtons, RerunForm } from "@/components/analysis-actions";
import { AnalysisProgress } from "@/components/analysis-progress";

const POLL_MS = 2000;
const FINAL: AnalysisStatus[] = ["done", "failed"];
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
    return error ? (
      <p className="text-sm text-destructive">
        Could not load analysis: {error}
      </p>
    ) : (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <Skeleton className="h-64 w-full rounded-2xl" />
      </div>
    );
  }

  if (!FINAL.includes(analysis.status))
    return <AnalysisProgress stage={analysis.status} />;

  if (analysis.status === "failed") {
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col items-center gap-4 rounded-2xl border bg-card p-8 text-center shadow-sm">
        <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangleIcon className="size-6" />
        </span>
        <h1 className="text-xl font-semibold">
          This analysis didn&apos;t finish
        </h1>
        <p className="text-muted-foreground">{analysis.error}</p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button nativeButton={false} render={<Link href="/analyze" />}>
            Start a new analysis
          </Button>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/settings" />}
          >
            Check AI settings
          </Button>
        </div>
      </div>
    );
  }

  const requirements = analysis.job_requirements;
  const profile = analysis.student_profile;
  const matches = analysis.matches ?? [];
  const counts = {
    strong: matches.filter((m) => m.bucket === "strong_in_resume").length,
    improve: matches.filter(
      (m) =>
        m.bucket === "weak_in_resume" ||
        m.bucket === "missing_from_resume_but_evidenced",
    ).length,
    gaps: matches.filter((m) => m.bucket === "true_gap").length,
  };
  const suggestions = analysis.suggestions ?? [];
  const pathSteps = analysis.learning_path?.steps.length ?? 0;

  return (
    <div className="flex w-full flex-col gap-6">
      {/* Summary */}
      <section className="relative overflow-hidden rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
        <div
          className="bg-brand-gradient absolute -top-24 -right-24 size-72 rounded-full opacity-10 blur-3xl"
          aria-hidden
        />
        <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">
              {new Date(analysis.created_at).toLocaleDateString(undefined, {
                dateStyle: "medium",
              })}
            </p>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              {requirements?.role_title ?? "Job analysis"}
            </h1>
            {requirements?.company && (
              <p className="text-muted-foreground">{requirements.company}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <Pill className="bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
                {counts.strong} strong
              </Pill>
              <Pill className="bg-amber-500/10 text-amber-700 dark:text-amber-400">
                {counts.improve} to improve
              </Pill>
              <Pill className="bg-rose-500/10 text-rose-700 dark:text-rose-400">
                {counts.gaps} gaps
              </Pill>
            </div>
            <div className="mt-3">
              <ExportButtons analysisId={analysis.id} />
            </div>
          </div>
          {analysis.fit_score != null && (
            <div className="flex justify-center gap-6 sm:gap-10">
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
        </div>
      </section>

      <Tabs defaultValue="overview" className="flex flex-col gap-4">
        <TabsList className="w-full justify-start overflow-x-auto print:hidden">
          <TabsTrigger value="overview">
            <LayoutListIcon />
            Overview
          </TabsTrigger>
          <TabsTrigger value="improve">
            <WandSparklesIcon />
            Improve resume
            {suggestions.length > 0 && <Count>{suggestions.length}</Count>}
          </TabsTrigger>
          <TabsTrigger value="learn">
            <BookOpenCheckIcon />
            Learn
            {pathSteps > 0 && <Count>{pathSteps}</Count>}
          </TabsTrigger>
          <TabsTrigger value="interview">
            <MessagesSquareIcon />
            Interview
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="flex flex-col gap-6">
          <p className="text-sm text-muted-foreground">
            The score weighs each requirement by importance and by how clearly
            your resume shows it. The same resume and job always get the same
            score.
          </p>
          {matches.length > 0 && <RequirementBreakdown matches={matches} />}
        </TabsContent>

        <TabsContent value="improve">
          <SuggestionList
            suggestions={suggestions}
            rejectedCount={analysis.rejected_suggestions?.length ?? 0}
            fitScore={analysis.fit_score}
            potentialScore={analysis.potential_score}
          />
        </TabsContent>

        <TabsContent value="learn" className="flex flex-col gap-6">
          {analysis.gaps && <GapList gaps={analysis.gaps} />}
          {analysis.learning_path && pathSteps > 0 ? (
            <LearningPathView path={analysis.learning_path} />
          ) : (
            <p className="rounded-2xl border bg-card p-6 text-sm text-muted-foreground">
              Nothing to learn for this job: every requirement is covered by
              what you already have.
            </p>
          )}
        </TabsContent>

        <TabsContent value="interview">
          <InterviewPrep analysisId={analysis.id} />
        </TabsContent>
      </Tabs>

      <RerunForm analysisId={analysis.id} />

      {(requirements || profile) && (
        <details className="rounded-2xl border bg-card p-4 text-sm print:hidden">
          <summary className="cursor-pointer text-muted-foreground">
            Raw extraction data · AI calls: {analysis.llm_usage.calls} (
            {analysis.llm_usage.cached_calls} from cache)
          </summary>
          <div className="mt-4 flex flex-col gap-4">
            {requirements && (
              <JsonBlock title="Job requirements" data={requirements} />
            )}
            {profile && <JsonBlock title="Your profile" data={profile} />}
          </div>
        </details>
      )}
    </div>
  );
}

function Pill({
  className,
  children,
}: {
  className: string;
  children: React.ReactNode;
}) {
  return (
    <span className={cn("rounded-full px-2.5 py-1 font-medium", className)}>
      {children}
    </span>
  );
}

function Count({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-primary/10 px-1.5 text-xs font-semibold text-primary tabular-nums">
      {children}
    </span>
  );
}

function JsonBlock({ title, data }: { title: string; data: unknown }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="font-medium">{title}</h3>
      <pre className="max-h-[32rem] overflow-auto rounded-lg bg-muted p-4 text-xs">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
