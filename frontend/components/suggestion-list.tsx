"use client";

import { useState } from "react";
import { ArrowRightIcon, TargetIcon, WandSparklesIcon } from "lucide-react";
import { toast } from "sonner";
import type { Gap, Suggestion } from "@/lib/types";
import { afterAddingText, whereToAdd } from "@/lib/results";
import { ScoreGauge } from "@/components/score-gauge";
import { ExplainButton, ExplainPanel, useExplain } from "@/components/explain";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy. Select the text and copy it manually.");
    }
  }
  return (
    <Button variant="outline" size="sm" onClick={copy}>
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

function SuggestionCard({ suggestion: s }: { suggestion: Suggestion }) {
  const explain = useExplain("suggestion", s.id);
  return (
    <Card className="border-l-4 border-l-primary">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <WandSparklesIcon className="size-4 text-primary" />
          {s.requirement_names.join(", ")}
          {s.uplift > 0 && (
            <Badge className="ml-auto bg-emerald-600 text-white dark:bg-emerald-500">
              +{s.uplift} points
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          Where: {whereToAdd(s.section, s.target)}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Add this line
          </p>
          <div className="flex items-start gap-3 rounded-md border bg-muted/40 p-3">
            <p className="flex-1">{s.suggested_text}</p>
            <CopyButton text={s.suggested_text} />
          </div>
        </div>
        <p>
          <span className="font-medium">Why it helps: </span>
          <span className="text-muted-foreground">{s.rationale}</span>
        </p>
        <p className="text-xs text-muted-foreground">
          Based on what you wrote in {s.quote_source_label}:{" "}
          <q className="italic">{s.quote}</q>
        </p>
        <ExplainButton explain={explain} className="-ml-2 self-start" />
        <ExplainPanel explain={explain} />
      </CardContent>
    </Card>
  );
}

export function SuggestionList({
  suggestions,
  rejectedCount,
  potentialScore,
  fitScore,
  finalScore = null,
  potentialFinalScore = null,
}: {
  suggestions: Suggestion[];
  rejectedCount: number;
  potentialScore: number | null;
  fitScore: number | null;
  finalScore?: number | null;
  potentialFinalScore?: number | null;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <WandSparklesIcon className="size-5 text-primary" />
          Already have it? Add it to your resume
        </h2>
        <p className="text-sm text-muted-foreground">
          {suggestions.length > 0
            ? "Each suggestion uses only what you gave us."
            : "Nothing to add yet."}
        </p>
      </div>
      {fitScore != null && potentialScore != null && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 sm:flex-row sm:gap-8">
            <div className="flex items-start gap-2 sm:gap-4">
              <ScoreGauge score={fitScore} label="Job fit now" />
              <ArrowRightIcon
                className="mt-14 size-5 shrink-0 text-muted-foreground sm:mt-16"
                aria-hidden
              />
              <ScoreGauge
                score={potentialScore}
                label="After adding what you have"
              />
            </div>
            <div className="flex flex-col gap-2 text-sm leading-relaxed">
              <p>{afterAddingText(fitScore, potentialScore)}</p>
              {finalScore != null &&
                potentialFinalScore != null &&
                potentialFinalScore > finalScore && (
                  <p className="text-muted-foreground">
                    Your final score (job fit + ATS) would go from {finalScore}%
                    to {potentialFinalScore}%.
                  </p>
                )}
            </div>
          </CardContent>
        </Card>
      )}
      {suggestions.map((s) => (
        <SuggestionCard key={s.id} suggestion={s} />
      ))}
      {rejectedCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {rejectedCount} AI-drafted{" "}
          {rejectedCount === 1 ? "suggestion was" : "suggestions were"} removed
          because {rejectedCount === 1 ? "it wasn't" : "they weren't"} backed by
          your documents.
        </p>
      )}
    </section>
  );
}

export function GapList({ gaps }: { gaps: Gap[] }) {
  if (gaps.length === 0) return null;
  const sorted = [...gaps].sort(
    (a, b) =>
      Number(b.importance === "must") - Number(a.importance === "must") ||
      a.requirement_index - b.requirement_index,
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TargetIcon className="size-4 text-rose-500" />
          Still to learn ({gaps.length})
        </CardTitle>
        <CardDescription>
          The job asks for these, and nothing you gave us shows them yet. These
          are what to learn next.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-wrap gap-2">
          {sorted.map((g) => (
            <li key={g.requirement_index}>
              <Badge
                variant={g.importance === "must" ? "destructive" : "outline"}
              >
                {g.name}
                {g.importance === "must" ? " · must have" : ""}
              </Badge>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
