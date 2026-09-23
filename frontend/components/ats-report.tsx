"use client";

import {
  CheckCircle2Icon,
  CircleAlertIcon,
  CircleXIcon,
  ScanTextIcon,
} from "lucide-react";
import { cn } from "cn";
import type { AtsCheck, AtsReport } from "@/lib/types";
import { ATS_GROUP_TITLE, atsIssues, keywordHint, plural } from "@/lib/results";
import { ExplainButton, ExplainPanel, useExplain } from "@/components/explain";
import { ScoreGauge } from "@/components/score-gauge";
import { Card, CardContent } from "@/components/ui/card";

const STATUS = {
  pass: {
    icon: CheckCircle2Icon,
    label: "Looks good",
    className: "text-emerald-600 dark:text-emerald-400",
  },
  warn: {
    icon: CircleAlertIcon,
    label: "Could be better",
    className: "text-amber-500 dark:text-amber-400",
  },
  fail: {
    icon: CircleXIcon,
    label: "Needs fixing",
    className: "text-rose-600 dark:text-rose-400",
  },
} as const;

const GROUPS: AtsCheck["group"][] = ["readable", "sections", "keywords"];

function CheckRow({ check }: { check: AtsCheck }) {
  const explain = useExplain("ats_check", check.id);
  const status = STATUS[check.status];
  const Icon = status.icon;
  return (
    <li className="flex flex-col gap-2 rounded-xl border bg-background p-4">
      <div className="flex items-start gap-3">
        <Icon
          className={cn("mt-0.5 size-5 shrink-0", status.className)}
          aria-label={status.label}
        />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <h4 className="font-medium">{check.title}</h4>
            <span className="text-xs text-muted-foreground tabular-nums">
              {check.points % 1 === 0 ? check.points : check.points.toFixed(1)}{" "}
              / {check.max_points} points
            </span>
          </div>
          <p className="text-sm text-muted-foreground">{check.detail}</p>
          {check.fix && (
            <p className="text-sm">
              <span className="font-medium">How to fix: </span>
              {check.fix}
            </p>
          )}
          {check.items.length > 0 && check.id !== "keywords" && (
            <ul className="mt-1 flex flex-wrap gap-1.5">
              {check.items.map((item) => (
                <li
                  key={item}
                  className="rounded-full bg-muted px-2 py-0.5 text-xs"
                >
                  {item}
                </li>
              ))}
            </ul>
          )}
        </div>
        <ExplainButton explain={explain} className="-mt-1 shrink-0" />
      </div>
      <ExplainPanel explain={explain} />
    </li>
  );
}

function Keywords({ report }: { report: AtsReport }) {
  if (report.keywords.length === 0) return null;
  const found = report.keywords.filter((k) => k.found);
  const missing = report.keywords.filter((k) => !k.found);
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-background p-4">
      <div>
        <h4 className="text-sm font-medium">In your resume ({found.length})</h4>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {found.map((k) => (
            <li
              key={k.requirement_index}
              className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-700 dark:text-emerald-400"
            >
              {k.name}
            </li>
          ))}
          {found.length === 0 && (
            <li className="text-sm text-muted-foreground">None yet.</li>
          )}
        </ul>
      </div>
      {missing.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">
            Not in your resume ({missing.length})
          </h4>
          <ul className="mt-2 flex flex-col gap-1.5">
            {missing.map((k) => (
              <li
                key={k.requirement_index}
                className="flex flex-wrap items-baseline gap-x-2 text-sm"
              >
                <span className="rounded-full bg-rose-500/10 px-2 py-0.5 text-xs font-medium text-rose-700 dark:text-rose-400">
                  {k.name}
                  {k.importance === "must" ? " · must-have" : ""}
                </span>
                <span className="text-muted-foreground">
                  {keywordHint(k.bucket)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function AtsReportView({ report }: { report: AtsReport }) {
  const explain = useExplain("ats");
  const issues = atsIssues(report.checks);
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <ScanTextIcon className="size-5 text-primary" />
          ATS check
        </h2>
        <p className="text-sm text-muted-foreground">
          Many employers use an applicant tracking system (ATS): software that
          reads your resume file and ranks it by the job&apos;s keywords before
          a person sees it. These checks show how well it can read yours.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center gap-4 sm:flex-row sm:gap-8">
          <ScoreGauge score={report.score} label="ATS score" />
          <div className="flex flex-1 flex-col gap-2 text-sm leading-relaxed">
            <p>
              {issues.length === 0
                ? "Hiring software can read your resume well and finds the job's keywords."
                : `${plural(issues.length, "thing")} to fix. Each one is a small change to your resume file.`}
            </p>
            {report.potential_score > report.score && (
              <p className="text-muted-foreground">
                Adding the lines in Improve resume would also add job keywords:
                ATS score {report.score}% → {report.potential_score}%.
              </p>
            )}
            <ExplainButton
              explain={explain}
              label="What does this score mean?"
              className="-ml-2 self-start"
            />
          </div>
        </CardContent>
        <CardContent>
          <ExplainPanel explain={explain} />
        </CardContent>
      </Card>

      {GROUPS.map((group) => {
        const checks = report.checks.filter((c) => c.group === group);
        if (checks.length === 0) return null;
        // Problems first, so the list reads as a to-do list.
        const order = { fail: 0, warn: 1, pass: 2 };
        checks.sort((a, b) => order[a.status] - order[b.status]);
        return (
          <div key={group} className="flex flex-col gap-2">
            <h3 className="font-semibold tracking-tight">
              {ATS_GROUP_TITLE[group]}
            </h3>
            <ul className="flex flex-col gap-2">
              {checks.map((c) => (
                <CheckRow key={c.id} check={c} />
              ))}
            </ul>
            {group === "keywords" && <Keywords report={report} />}
          </div>
        );
      })}
    </section>
  );
}
