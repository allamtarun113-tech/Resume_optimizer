"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import type { AnalysisResponse, AnalysisStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  scoring: "Scoring",
  advising: "Writing suggestions",
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
          <CardTitle className="flex items-center gap-3">
            Analysis
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
          {usage.calls > 0 && (
            <p className="text-muted-foreground">
              AI calls: {usage.calls} ({usage.cached_calls} from cache) · tokens
              in {usage.input_tokens.toLocaleString()} / out{" "}
              {usage.output_tokens.toLocaleString()}
            </p>
          )}
          {profile && requirements && (
            <p>
              Found {profile.skills.length} skill mentions,{" "}
              {profile.projects.length} projects, {profile.experience.length}{" "}
              roles, and {requirements.requirements.length} job requirements.
            </p>
          )}
          <div>
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/analyze" />}
            >
              New analysis
            </Button>
          </div>
        </CardContent>
      </Card>

      {requirements && (
        <JsonCard
          title="Job requirements"
          description={
            requirements.role_title ?? "Extracted from the job description"
          }
          data={requirements}
        />
      )}
      {profile && (
        <JsonCard
          title="Your profile"
          description="Extracted from your resume and supporting documents"
          data={profile}
        />
      )}
    </div>
  );
}

// Phase 1 debug view: raw extraction output. Later phases replace it with real UI.
function JsonCard({
  title,
  description,
  data,
}: {
  title: string;
  description: string;
  data: unknown;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <pre className="max-h-[32rem] overflow-auto rounded-md bg-muted p-4 text-xs">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CardContent>
    </Card>
  );
}
