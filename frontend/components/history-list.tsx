"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { apiDelete, apiFetch } from "@/lib/api";
import type { AnalysisSummary } from "@/lib/types";
import { scoreTone } from "@/lib/results";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const TONE_CLASS = {
  good: "text-emerald-600 dark:text-emerald-400",
  ok: "text-amber-600 dark:text-amber-400",
  low: "text-rose-600 dark:text-rose-400",
};

export function HistoryList() {
  const [items, setItems] = useState<AnalysisSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AnalysisSummary[]>("/analyses")
      .then(setItems)
      .catch((e) => setError((e as Error).message));
  }, []);

  async function remove(item: AnalysisSummary) {
    const label = item.role_title ?? "this analysis";
    if (!window.confirm(`Delete ${label}? This can't be undone.`)) return;
    try {
      await apiDelete(`/analyses/${item.id}`);
      setItems((current) => current?.filter((i) => i.id !== item.id) ?? null);
      toast.success("Analysis deleted.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (error) {
    return (
      <p className="text-sm text-destructive">
        Could not load your analyses: {error}
      </p>
    );
  }
  if (!items) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-start gap-3 py-6">
          <p>You haven&apos;t analysed a job yet.</p>
          <Button nativeButton={false} render={<Link href="/analyze" />}>
            Start your first analysis
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.id}>
          <Card>
            <CardContent className="flex flex-wrap items-center gap-4 py-4">
              <div className="w-14 text-center">
                {item.fit_score != null ? (
                  <span
                    className={`text-2xl font-semibold ${TONE_CLASS[scoreTone(item.fit_score)]}`}
                  >
                    {item.fit_score}%
                  </span>
                ) : (
                  <span className="text-muted-foreground">–</span>
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <Link
                  href={`/analysis/${item.id}`}
                  className="truncate font-medium underline-offset-4 hover:underline"
                >
                  {item.role_title ?? "Untitled job"}
                  {item.company ? ` · ${item.company}` : ""}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {new Date(item.created_at).toLocaleString()}
                  {item.potential_score != null &&
                    item.fit_score != null &&
                    item.potential_score > item.fit_score &&
                    ` · up to ${item.potential_score}% with what you already have`}
                </span>
              </div>
              {item.status !== "done" && (
                <Badge
                  variant={
                    item.status === "failed" ? "destructive" : "secondary"
                  }
                >
                  {item.status === "failed" ? "Failed" : "In progress"}
                </Badge>
              )}
              <Button variant="ghost" size="sm" onClick={() => remove(item)}>
                Delete
              </Button>
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
