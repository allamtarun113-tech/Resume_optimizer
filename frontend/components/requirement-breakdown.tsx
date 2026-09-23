"use client";

import {
  CheckCircle2Icon,
  CircleDashedIcon,
  FilePlus2Icon,
  TargetIcon,
} from "lucide-react";
import type { RequirementMatch } from "@/lib/types";
import {
  type Bucket,
  evidenceWhere,
  groupMatches,
  plainStatus,
} from "@/lib/results";
import { ExplainButton, ExplainPanel, useExplain } from "@/components/explain";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function MatchRow({ match }: { match: RequirementMatch }) {
  const explain = useExplain("requirement", String(match.requirement_index));
  const direct = match.evidence.filter((e) => e.direct);
  const shown = (direct.length ? direct : match.evidence).slice(0, 4);

  return (
    <li className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{match.name}</span>
            <Badge
              variant={match.importance === "must" ? "default" : "outline"}
            >
              {match.importance === "must" ? "Must have" : "Nice to have"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">{plainStatus(match)}</p>
        </div>
        <ExplainButton explain={explain} />
      </div>
      {shown.length > 0 && (
        <details className="group text-sm">
          <summary className="w-fit cursor-pointer list-none text-xs font-medium text-muted-foreground hover:text-foreground">
            <span className="group-open:hidden">▸ Where we found it</span>
            <span className="hidden group-open:inline">
              ▾ Where we found it
            </span>
          </summary>
          <ul className="mt-2 flex flex-col gap-2 border-l-2 pl-3">
            {shown.map((e) => (
              <li key={`${e.kind}-${e.index}`} className="flex flex-col">
                <span>
                  <span className="font-medium">{e.label}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    · {evidenceWhere(e)}
                  </span>
                </span>
                {e.snippet && e.snippet !== e.label && (
                  <q className="text-xs text-muted-foreground italic">
                    {e.snippet}
                  </q>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      <ExplainPanel explain={explain} />
    </li>
  );
}

const BUCKET_STYLE: Record<
  Bucket,
  { icon: React.ComponentType<{ className?: string }>; tone: string }
> = {
  strong_in_resume: {
    icon: CheckCircle2Icon,
    tone: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  weak_in_resume: {
    icon: CircleDashedIcon,
    tone: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  missing_from_resume_but_evidenced: {
    icon: FilePlus2Icon,
    tone: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
  },
  true_gap: {
    icon: TargetIcon,
    tone: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
  },
};

export function RequirementBreakdown({
  matches,
  skip = [],
}: {
  matches: RequirementMatch[];
  skip?: Bucket[];
}) {
  return (
    <div className="flex flex-col gap-6">
      {groupMatches(matches, skip).map((group) => {
        const { icon: Icon, tone } = BUCKET_STYLE[group.bucket];
        return (
          <Card key={group.bucket}>
            <CardHeader>
              <div className="flex items-start gap-3">
                <span
                  className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${tone}`}
                >
                  <Icon className="size-4" />
                </span>
                <div className="flex flex-col gap-1">
                  <CardTitle>
                    {group.title}{" "}
                    <span className="text-muted-foreground">
                      ({group.items.length})
                    </span>
                  </CardTitle>
                  <CardDescription>{group.description}</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {group.items.map((m) => (
                  <MatchRow key={m.requirement_index} match={m} />
                ))}
              </ul>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
