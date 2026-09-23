"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRightIcon,
  FilePlus2Icon,
  HistoryIcon,
  KeyRoundIcon,
  SettingsIcon,
  TrendingUpIcon,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { AiSettings, AnalysisSummary } from "@/lib/types";
import { scoreTone } from "@/lib/results";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TONE_TEXT = {
  good: "text-emerald-600 dark:text-emerald-400",
  ok: "text-amber-600 dark:text-amber-400",
  low: "text-rose-600 dark:text-rose-400",
};

function firstName(email: string): string {
  const name = email.split("@")[0].split(/[.+_-]/)[0];
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function Dashboard({ email }: { email: string }) {
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [items, setItems] = useState<AnalysisSummary[] | null>(null);

  useEffect(() => {
    apiFetch<AiSettings>("/settings/ai")
      .then(setAi)
      .catch(() => null);
    apiFetch<AnalysisSummary[]>("/analyses")
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  const done = (items ?? []).filter((i) => i.fit_score != null);
  const best = done.length ? Math.max(...done.map((i) => i.fit_score!)) : null;
  const latest = done[0]?.fit_score ?? null;

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Welcome back</p>
          <h1 className="text-3xl font-semibold tracking-tight">
            Hi, {firstName(email)}
          </h1>
        </div>
        <Button
          size="lg"
          nativeButton={false}
          render={<Link href="/analyze" />}
        >
          <FilePlus2Icon />
          New analysis
        </Button>
      </div>

      {ai && !ai.has_key && (
        <div className="flex flex-col gap-4 rounded-2xl border border-primary/30 bg-primary/5 p-5 sm:flex-row sm:items-center">
          <span className="bg-brand-gradient flex size-11 shrink-0 items-center justify-center rounded-xl text-white">
            <KeyRoundIcon className="size-5" />
          </span>
          <div className="flex-1">
            <p className="font-semibold">Add your OpenAI key to get started</p>
            <p className="text-sm text-muted-foreground">
              Analyses run on your own OpenAI account, about $0.002 each. It
              takes a minute to set up.
            </p>
          </div>
          <Button nativeButton={false} render={<Link href="/settings" />}>
            Add key
            <ArrowRightIcon />
          </Button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Analyses"
          value={items ? String(items.length) : null}
        />
        <StatCard
          label="Latest fit score"
          value={latest != null ? `${latest}%` : items ? "–" : null}
          tone={latest != null ? scoreTone(latest) : undefined}
        />
        <StatCard
          label="Best fit score"
          value={best != null ? `${best}%` : items ? "–" : null}
          tone={best != null ? scoreTone(best) : undefined}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <HistoryIcon className="size-4 text-primary" />
              Recent analyses
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              nativeButton={false}
              render={<Link href="/history" />}
            >
              View all
            </Button>
          </CardHeader>
          <CardContent>
            {items === null ? (
              <div className="flex flex-col gap-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            ) : items.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-10 text-center">
                <TrendingUpIcon className="size-8 text-muted-foreground" />
                <p className="text-muted-foreground">
                  Your analyses will show up here.
                </p>
                <Button nativeButton={false} render={<Link href="/analyze" />}>
                  Run your first analysis
                </Button>
              </div>
            ) : (
              <ul className="flex flex-col divide-y">
                {items.slice(0, 5).map((item) => (
                  <li key={item.id}>
                    <Link
                      href={`/analysis/${item.id}`}
                      className="flex items-center gap-4 rounded-lg px-2 py-3 transition-colors hover:bg-muted/60"
                    >
                      <span
                        className={`w-12 text-lg font-semibold tabular-nums ${
                          item.fit_score != null
                            ? TONE_TEXT[scoreTone(item.fit_score)]
                            : "text-muted-foreground"
                        }`}
                      >
                        {item.fit_score != null ? `${item.fit_score}%` : "–"}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">
                          {item.role_title ?? "Untitled job"}
                        </span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {item.company ? `${item.company} · ` : ""}
                          {new Date(item.created_at).toLocaleDateString()}
                        </span>
                      </span>
                      <ArrowRightIcon className="size-4 text-muted-foreground" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <QuickLink
            href="/analyze"
            icon={FilePlus2Icon}
            title="Analyze a job"
            text="Resume + job description → score, suggestions, plan."
          />
          <QuickLink
            href="/history"
            icon={HistoryIcon}
            title="Your history"
            text="Reopen results, try another job, export reports."
          />
          <QuickLink
            href="/settings"
            icon={SettingsIcon}
            title="AI settings"
            text={
              ai?.has_key
                ? `Key •••• ${ai.key_last4} · ${ai.model_small}`
                : "Add your OpenAI key and choose a model."
            }
          />
        </div>
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | null;
  tone?: keyof typeof TONE_TEXT;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 py-5">
        <span className="text-sm text-muted-foreground">{label}</span>
        {value === null ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <span
            className={`text-3xl font-semibold tabular-nums ${tone ? TONE_TEXT[tone] : ""}`}
          >
            {value}
          </span>
        )}
      </CardContent>
    </Card>
  );
}

function QuickLink({
  href,
  icon: Icon,
  title,
  text,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  text: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-start gap-3 rounded-xl border bg-card p-4 transition-shadow hover:shadow-md hover:shadow-primary/5"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
        <Icon className="size-4" />
      </span>
      <span className="min-w-0">
        <span className="block font-medium">{title}</span>
        <span className="block truncate text-sm text-muted-foreground">
          {text}
        </span>
      </span>
    </Link>
  );
}
