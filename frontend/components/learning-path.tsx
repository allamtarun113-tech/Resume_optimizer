"use client";

import { BookOpenCheckIcon } from "lucide-react";
import type { LearningPath, LearningStep } from "@/lib/types";
import { formatHours } from "@/lib/results";
import { ExplainButton, ExplainPanel, useExplain } from "@/components/explain";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const TYPE_LABEL: Record<string, string> = {
  docs: "Docs",
  course: "Course",
  video: "Video",
  book: "Book",
  practice: "Practice",
};

export function LearningPathView({ path }: { path: LearningPath }) {
  if (path.steps.length === 0) return null;
  const total = formatHours(path.total_hours);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpenCheckIcon className="size-4 text-primary" />
          Your learning path
        </CardTitle>
        <CardDescription>
          Learn these in order, since earlier steps are what later ones build
          on.
          {total && ` In total: ${total} with the first resource of each step.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="relative flex flex-col gap-6 border-l pl-6">
          {path.steps.map((step) => (
            <StepItem key={`${step.step}-${step.name}`} step={step} />
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function StepItem({ step }: { step: LearningStep }) {
  const explain = useExplain("learning_step", String(step.step));
  const hours = formatHours(step.est_hours);
  return (
    <li className="relative">
      <span
        className="bg-brand-gradient absolute -left-[2.2rem] flex size-6 items-center justify-center rounded-full text-xs font-semibold text-white"
        aria-hidden
      >
        {step.step}
      </span>
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{step.name}</span>
          {step.kind === "prerequisite" ? (
            <Badge variant="secondary">Foundation</Badge>
          ) : (
            <Badge variant="outline">Job requirement</Badge>
          )}
          {hours && (
            <span className="text-xs text-muted-foreground">{hours}</span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{step.why}</p>
        {step.resources.length > 0 ? (
          <ul className="flex flex-col gap-1 text-sm">
            {step.resources.map((r) => (
              <li key={r.url} className="flex flex-wrap gap-x-2">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  {r.title}
                </a>
                <span className="text-xs text-muted-foreground">
                  {TYPE_LABEL[r.type] ?? r.type} · {r.level}
                  {r.free ? " · free" : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">
            No curated resource yet. Search the official documentation for{" "}
            {step.name}.
          </p>
        )}
        <ExplainButton explain={explain} className="-ml-2 self-start" />
        <ExplainPanel explain={explain} />
      </div>
    </li>
  );
}
