import {
  CheckCircle2Icon,
  CircleDashedIcon,
  FilePlus2Icon,
  TargetIcon,
} from "lucide-react";
import type { RequirementMatch } from "@/lib/types";
import {
  type Bucket,
  groupMatches,
  sourceLabel,
  strengthLabel,
} from "@/lib/results";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const CATEGORY_LABEL: Record<RequirementMatch["category"], string> = {
  skill: "Skill",
  domain: "Domain",
  experience: "Experience",
  education: "Education",
  soft_skill: "Soft skill",
};

function StrengthBar({ value }: { value: number }) {
  return (
    <div
      className="h-1.5 w-20 overflow-hidden rounded-full bg-muted"
      aria-hidden
    >
      <div
        className="h-full rounded-full bg-primary"
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  );
}

function MatchRow({ match }: { match: RequirementMatch }) {
  const direct = match.evidence.filter((e) => e.direct);
  const shown = (direct.length ? direct : match.evidence).slice(0, 4);
  const showBest =
    match.best_strength > match.resume_strength &&
    match.bucket !== "strong_in_resume";

  return (
    <li className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{match.name}</span>
        <Badge variant={match.importance === "must" ? "default" : "outline"}>
          {match.importance === "must" ? "Must have" : "Nice to have"}
        </Badge>
        <Badge variant="secondary">{CATEGORY_LABEL[match.category]}</Badge>
        <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          <StrengthBar value={match.resume_strength} />
          {strengthLabel(match.resume_strength)}
          {showBest &&
            ` → ${strengthLabel(match.best_strength)} with your docs`}
        </span>
      </div>
      {match.min_years != null && (
        <p className="text-xs text-muted-foreground">
          Needs {match.min_years}+ years
          {match.total_years != null &&
            ` · you have about ${match.total_years.toFixed(1)} years of matching experience`}
        </p>
      )}
      {shown.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
          {shown.map((e) => (
            <li key={`${e.kind}-${e.index}`}>
              <span className="text-foreground">{e.label}</span>
              {" · "}
              {e.kind === "skill" ? e.context.replace("_", " ") : e.kind}
              {" · "}
              {sourceLabel(e.source)}
              {!e.direct && " · related"}
            </li>
          ))}
        </ul>
      )}
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
