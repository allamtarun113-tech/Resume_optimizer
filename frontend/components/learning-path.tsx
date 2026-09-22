import type { LearningPath } from "@/lib/types";
import { formatHours } from "@/lib/results";
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
        <CardTitle>Your learning path</CardTitle>
        <CardDescription>
          Learn these in order, since earlier steps are what later ones build
          on.
          {total && ` In total: ${total} with the first resource of each step.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="relative flex flex-col gap-6 border-l pl-6">
          {path.steps.map((step) => {
            const hours = formatHours(step.est_hours);
            return (
              <li key={`${step.step}-${step.name}`} className="relative">
                <span
                  className="absolute -left-[2.1rem] flex size-6 items-center justify-center rounded-full border bg-background text-xs font-medium"
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
                      <span className="text-xs text-muted-foreground">
                        {hours}
                      </span>
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
                      No curated resource yet. Search the official documentation
                      for {step.name}.
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
