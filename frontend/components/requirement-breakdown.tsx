import type { RequirementMatch } from "@/lib/types";
import { groupMatches, sourceLabel, strengthLabel } from "@/lib/results";
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

export function RequirementBreakdown({
  matches,
}: {
  matches: RequirementMatch[];
}) {
  return (
    <div className="flex flex-col gap-6">
      {groupMatches(matches).map((group) => (
        <Card key={group.bucket}>
          <CardHeader>
            <CardTitle>
              {group.title}{" "}
              <span className="text-muted-foreground">
                ({group.items.length})
              </span>
            </CardTitle>
            <CardDescription>{group.description}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {group.items.map((m) => (
                <MatchRow key={m.requirement_index} match={m} />
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
