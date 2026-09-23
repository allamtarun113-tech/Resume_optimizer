"use client";

import { createContext, useContext, useState } from "react";
import Link from "next/link";
import { Loader2Icon, SparklesIcon, XIcon } from "lucide-react";
import { cn } from "cn";
import { apiPostJson } from "@/lib/api";
import { isNoKeyError } from "@/lib/errors";
import type { ExplainKind, ExplainRequest, Explanation } from "@/lib/types";
import { Button } from "@/components/ui/button";

// "Explain" buttons on the results page. Each asks the backend to explain one item in
// plain English; the backend picks the facts from the stored analysis and caches the
// answer, so opening the same explanation again is free and instant.

export const AnalysisIdContext = createContext<string | null>(null);

// Answers already loaded in this tab, so re-opening doesn't wait.
const loaded = new Map<string, Explanation>();

type State =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "open"; explanation: Explanation }
  | { status: "error"; message: string; noKey: boolean };

export type ExplainState = {
  state: State;
  toggle: () => void;
  close: () => void;
};

export function useExplain(kind: ExplainKind, ref: string = ""): ExplainState {
  const analysisId = useContext(AnalysisIdContext);
  const [state, setState] = useState<State>({ status: "closed" });
  const key = `${analysisId}|${kind}|${ref}`;

  async function open() {
    const cached = loaded.get(key);
    if (cached) return setState({ status: "open", explanation: cached });
    setState({ status: "loading" });
    try {
      const body: ExplainRequest = { kind, ref };
      const explanation = await apiPostJson<Explanation>(
        `/analyses/${analysisId}/explain`,
        body,
      );
      loaded.set(key, explanation);
      setState({ status: "open", explanation });
    } catch (e) {
      setState({
        status: "error",
        message:
          (e as Error).message ||
          "Couldn't get an explanation. Please try again.",
        noKey: isNoKeyError(e),
      });
    }
  }

  return {
    state,
    toggle: () =>
      state.status === "closed" || state.status === "error"
        ? void open()
        : setState({ status: "closed" }),
    close: () => setState({ status: "closed" }),
  };
}

export function ExplainButton({
  explain,
  label = "Explain",
  className,
}: {
  explain: ExplainState;
  label?: string;
  className?: string;
}) {
  const { state } = explain;
  const expanded = state.status !== "closed";
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-expanded={expanded}
      disabled={state.status === "loading"}
      onClick={explain.toggle}
      className={cn(
        "shrink-0 text-primary hover:text-primary print:hidden",
        className,
      )}
    >
      {state.status === "loading" ? (
        <Loader2Icon className="animate-spin" />
      ) : (
        <SparklesIcon />
      )}
      {state.status === "loading"
        ? "Explaining…"
        : expanded
          ? "Hide explanation"
          : label}
    </Button>
  );
}

export function ExplainPanel({ explain }: { explain: ExplainState }) {
  const { state } = explain;
  if (state.status === "closed" || state.status === "loading") return null;

  if (state.status === "error") {
    return (
      <div
        className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm print:hidden"
        role="alert"
      >
        <p>{state.message}</p>
        {state.noKey && (
          <Link
            href="/settings"
            className="mt-2 inline-block font-medium text-primary underline-offset-4 hover:underline"
          >
            Open Settings
          </Link>
        )}
      </div>
    );
  }

  const { summary, details, next_steps } = state.explanation;
  return (
    <div
      className="relative flex flex-col gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4 pr-10 text-sm"
      role="region"
      aria-label="Explanation"
    >
      <button
        type="button"
        onClick={explain.close}
        aria-label="Close explanation"
        className="absolute top-3 right-3 rounded-md p-1 text-muted-foreground hover:bg-primary/10 print:hidden"
      >
        <XIcon className="size-4" />
      </button>
      <p className="flex gap-2 leading-relaxed">
        <SparklesIcon className="mt-0.5 size-4 shrink-0 text-primary" />
        <span>{summary}</span>
      </p>
      {details.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-10 text-muted-foreground">
          {details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
      {next_steps.length > 0 && (
        <div className="flex flex-col gap-1 pl-6">
          <p className="font-medium">What to do</p>
          <ol className="flex list-decimal flex-col gap-1 pl-4 text-muted-foreground">
            {next_steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      )}
      <p className="pl-6 text-xs text-muted-foreground">
        Written by AI from your analysis. Check it against your own documents.
      </p>
    </div>
  );
}
