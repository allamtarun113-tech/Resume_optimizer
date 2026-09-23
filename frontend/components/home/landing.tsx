import Link from "next/link";
import {
  ArrowRightIcon,
  BookOpenCheckIcon,
  FileSearchIcon,
  GaugeIcon,
  KeyRoundIcon,
  MessagesSquareIcon,
  SparklesIcon,
  TargetIcon,
  UploadCloudIcon,
  WandSparklesIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScoreGauge } from "@/components/score-gauge";

const FEATURES = [
  {
    icon: GaugeIcon,
    title: "Job Fit Score",
    text: "A clear percentage for how well your resume matches the job, calculated the same way every time.",
  },
  {
    icon: WandSparklesIcon,
    title: "Resume suggestions",
    text: "Ready-to-paste lines built only from things you've actually done, each showing the points it adds.",
  },
  {
    icon: TargetIcon,
    title: "Skill gaps",
    text: "See exactly which requirements you're missing, separated from what's just missing on paper.",
  },
  {
    icon: BookOpenCheckIcon,
    title: "Learning path",
    text: "An ordered plan with free, trusted courses and docs, starting with the foundations you need first.",
  },
  {
    icon: MessagesSquareIcon,
    title: "Interview prep",
    text: "Real questions for this job plus deep dives into your own projects, every one with its source.",
  },
  {
    icon: KeyRoundIcon,
    title: "Your key, your data",
    text: "Runs on your own OpenAI key, encrypted at rest. About $0.002 per analysis.",
  },
];

const STEPS = [
  {
    icon: UploadCloudIcon,
    title: "Upload",
    text: "Your resume, the job description, and anything else you've built.",
  },
  {
    icon: FileSearchIcon,
    title: "Analyze",
    text: "We match every requirement against your evidence in under a minute.",
  },
  {
    icon: SparklesIcon,
    title: "Improve",
    text: "Apply the suggestions, learn the gaps, and practise the interview.",
  },
];

export function Landing() {
  return (
    <main className="flex flex-col">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="bg-grid absolute inset-0 -z-10" aria-hidden />
        <div
          className="absolute top-[-10rem] left-1/2 -z-10 h-[28rem] w-[56rem] -translate-x-1/2 rounded-full bg-primary/15 blur-3xl"
          aria-hidden
        />
        <div className="mx-auto grid w-full max-w-6xl items-center gap-12 px-4 py-16 md:py-24 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="flex flex-col items-start gap-6">
            <span className="inline-flex items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
              <SparklesIcon className="size-3.5 text-primary" />
              For students and new grads
            </span>
            <h1 className="text-4xl leading-[1.05] font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
              Know exactly how you{" "}
              <span className="text-gradient">fit the job</span>
            </h1>
            <p className="max-w-xl text-lg text-pretty text-muted-foreground">
              Upload your resume and a job description. Get a job fit score,
              honest resume improvements, a learning path for your gaps, and the
              questions interviewers will ask.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                size="lg"
                nativeButton={false}
                render={<Link href="/login" />}
              >
                Get started free
                <ArrowRightIcon />
              </Button>
              <Button
                size="lg"
                variant="outline"
                nativeButton={false}
                render={<a href="#how-it-works" />}
              >
                How it works
              </Button>
            </div>
          </div>

          {/* Product preview */}
          <div className="relative">
            <div
              className="bg-brand-gradient absolute -inset-4 -z-10 rounded-3xl opacity-20 blur-2xl"
              aria-hidden
            />
            <div className="rounded-2xl border bg-card p-6 shadow-xl shadow-primary/10">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">
                    Backend Engineer
                  </p>
                  <p className="font-semibold">Example Corp</p>
                </div>
                <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                  +18 points available
                </span>
              </div>
              <div className="my-6 flex justify-center gap-8">
                <ScoreGauge score={64} label="Job fit" />
                <ScoreGauge score={82} label="With your projects" />
              </div>
              <div className="flex flex-col gap-2 text-sm">
                {[
                  ["Python", "Strong", "bg-emerald-500"],
                  ["Docker", "On your notes, not your resume", "bg-amber-500"],
                  ["Kubernetes", "Skill gap: learn next", "bg-rose-500"],
                ].map(([name, note, dot]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between rounded-lg border bg-muted/40 px-3 py-2"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      <span className={`size-2 rounded-full ${dot}`} />
                      {name}
                    </span>
                    <span className="text-muted-foreground">{note}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto w-full max-w-6xl px-4 py-16">
        <div className="mx-auto mb-10 max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight">
            Everything you need before you apply
          </h2>
          <p className="mt-3 text-muted-foreground">
            No invented skills, no guesswork: every suggestion and question is
            backed by your documents or a real source.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div
              key={title}
              className="group rounded-2xl border bg-card p-6 transition-shadow hover:shadow-lg hover:shadow-primary/5"
            >
              <span className="mb-4 inline-flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Icon className="size-5" />
              </span>
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="scroll-mt-20 border-y bg-muted/30">
        <div className="mx-auto w-full max-w-6xl px-4 py-16">
          <h2 className="mb-10 text-center text-3xl font-semibold tracking-tight">
            How it works
          </h2>
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <li
                key={title}
                className="flex flex-col items-center gap-3 text-center"
              >
                <span className="bg-brand-gradient flex size-12 items-center justify-center rounded-2xl text-white shadow-lg shadow-primary/25">
                  <Icon className="size-6" />
                </span>
                <span className="text-xs font-semibold tracking-widest text-primary uppercase">
                  Step {i + 1}
                </span>
                <h3 className="text-lg font-semibold">{title}</h3>
                <p className="max-w-xs text-sm text-muted-foreground">{text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto w-full max-w-6xl px-4 py-16">
        <div className="bg-brand-gradient relative overflow-hidden rounded-3xl px-6 py-12 text-center text-white shadow-xl shadow-primary/20 sm:px-12">
          <h2 className="text-3xl font-semibold tracking-tight">
            Ready to see where you stand?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-white/80">
            Create a free account, add your OpenAI key, and run your first
            analysis in a couple of minutes.
          </p>
          <Button
            size="lg"
            variant="secondary"
            className="mt-6"
            nativeButton={false}
            render={<Link href="/login" />}
          >
            Get started
            <ArrowRightIcon />
          </Button>
        </div>
      </section>
    </main>
  );
}
