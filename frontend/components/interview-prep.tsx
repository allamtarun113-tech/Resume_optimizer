"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CodeIcon,
  FolderGit2Icon,
  Loader2Icon,
  MessagesSquareIcon,
  UserIcon,
  UsersIcon,
} from "lucide-react";
import { showApiError } from "@/lib/errors";
import { ApiError, apiFetch } from "@/lib/api";
import type { InterviewQuestion, InterviewSet } from "@/lib/types";
import { groupByTopic, sourceText } from "@/lib/results";
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

function QuestionItem({ q, refId }: { q: InterviewQuestion; refId: string }) {
  const explain = useExplain("interview_question", refId);
  const source = sourceText(q.source);
  return (
    <li className="flex flex-col gap-1">
      <div className="flex flex-wrap items-start gap-x-2">
        <span className="min-w-0 flex-1">{q.text}</span>
        <ExplainButton
          explain={explain}
          label="What are they looking for?"
          className="-my-1"
        />
      </div>
      <span className="text-xs text-muted-foreground">
        {q.dimension && <span className="capitalize">{q.dimension} · </span>}
        {q.source.url ? (
          <a
            href={q.source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline-offset-4 hover:underline"
          >
            {source}
          </a>
        ) : (
          source
        )}
      </span>
      <ExplainPanel explain={explain} />
    </li>
  );
}

// `refs[i]` locates each question in the stored set, for its Explain button.
function QuestionList({
  questions,
  refs,
}: {
  questions: InterviewQuestion[];
  refs: string[];
}) {
  return (
    <ol className="flex list-decimal flex-col gap-3 pl-5 text-sm">
      {questions.map((q, i) => (
        <QuestionItem key={`${i}-${q.text}`} q={q} refId={refs[i]} />
      ))}
    </ol>
  );
}

const refsFor = (prefix: string, n: number) =>
  Array.from({ length: n }, (_, i) => `${prefix}:${i}`);

function Section({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" />
          </span>
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">{children}</CardContent>
    </Card>
  );
}

export function InterviewPrep({ analysisId }: { analysisId: string }) {
  const router = useRouter();
  const [set, setSet] = useState<InterviewSet | null>(null);
  const [checking, setChecking] = useState(true);
  const [preparing, setPreparing] = useState(false);

  // Show a previously generated set without making the user click again.
  useEffect(() => {
    let cancelled = false;
    apiFetch<InterviewSet>(`/analyses/${analysisId}/interview`)
      .then((data) => !cancelled && setSet(data))
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 404)) console.error(e);
      })
      .finally(() => !cancelled && setChecking(false));
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  async function prepare() {
    setPreparing(true);
    try {
      const data = await apiFetch<InterviewSet>(
        `/analyses/${analysisId}/interview`,
        { method: "POST" },
      );
      setSet(data);
    } catch (e) {
      showApiError(e, router.push);
    } finally {
      setPreparing(false);
    }
  }

  if (checking) return null;

  if (!set) {
    return (
      <Card className="relative overflow-hidden">
        <div
          className="bg-brand-gradient absolute -top-20 -right-20 size-56 rounded-full opacity-10 blur-3xl"
          aria-hidden
        />
        <CardHeader>
          <span className="bg-brand-gradient mb-2 flex size-11 items-center justify-center rounded-xl text-white shadow-lg shadow-primary/25">
            <MessagesSquareIcon className="size-5" />
          </span>
          <CardTitle className="text-lg">Prepare for the interview</CardTitle>
          <CardDescription>
            Real interview questions for this job, drawn from public question
            banks, plus deep questions about your own projects. Questions only,
            no answers: practise answering them out loud.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-4">
          <Button size="lg" onClick={prepare} disabled={preparing}>
            {preparing ? (
              <Loader2Icon className="animate-spin" />
            ) : (
              <MessagesSquareIcon />
            )}
            {preparing ? "Preparing…" : "Prepare Me for Interview"}
          </Button>
          {preparing && (
            <p className="text-sm text-muted-foreground">
              Picking questions for your projects and this job. This takes about
              half a minute.
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
        <MessagesSquareIcon className="size-5 text-primary" />
        Interview preparation
      </h2>

      {set.personal.length > 0 && (
        <Section
          icon={UserIcon}
          title="About you"
          description="Background questions most interviews start with."
        >
          <QuestionList
            questions={set.personal}
            refs={refsFor("personal", set.personal.length)}
          />
        </Section>
      )}

      {set.projects.length > 0 && (
        <Section
          icon={FolderGit2Icon}
          title="Your projects, in depth"
          description="Interviewers dig into what you built. Be ready to explain every decision."
        >
          {set.projects.map((p, pi) => (
            <div key={p.project} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-medium">{p.project}</h3>
                {p.technologies.slice(0, 5).map((t) => (
                  <Badge key={t} variant="secondary">
                    {t}
                  </Badge>
                ))}
              </div>
              <QuestionList
                questions={p.questions}
                refs={refsFor(`project:${pi}`, p.questions.length)}
              />
            </div>
          ))}
        </Section>
      )}

      {set.technical.length > 0 && (
        <Section
          icon={CodeIcon}
          title="Technical, for this job"
          description="Chosen for the job's requirements, most important first."
        >
          {groupByTopic(
            set.technical.map((q, i) => ({ ...q, ref: `technical:${i}` })),
          ).map((g) => (
            <div key={g.topic} className="flex flex-col gap-2">
              <h3 className="font-medium">{g.topic}</h3>
              <QuestionList
                questions={g.questions}
                refs={g.questions.map((q) => q.ref)}
              />
            </div>
          ))}
        </Section>
      )}

      {set.general.length > 0 && (
        <Section
          icon={UsersIcon}
          title="Behavioral"
          description="Answer with a real example: situation, what you did, and the result."
        >
          <QuestionList
            questions={set.general}
            refs={refsFor("general", set.general.length)}
          />
        </Section>
      )}
    </section>
  );
}
