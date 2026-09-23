import { CheckCircle2Icon } from "lucide-react";
import { AuthError } from "@/components/auth-error";
import { LoginForm } from "@/components/login-form";
import { BrandMark } from "@/components/layout/brand";
import { safeNextPath } from "@/lib/redirect";

const POINTS = [
  "A job fit score you can trust: same inputs, same score",
  "Resume lines built only from what you've actually done",
  "A learning path and real interview questions for the role",
];

export default async function LoginPage(props: PageProps<"/login">) {
  const { next, error } = await props.searchParams;
  const nextPath = safeNextPath(next);

  return (
    <main className="grid flex-1 lg:grid-cols-2">
      <section className="bg-brand-gradient relative hidden overflow-hidden p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          className="absolute -right-24 -bottom-24 size-96 rounded-full bg-white/10 blur-3xl"
          aria-hidden
        />
        <div className="flex items-center gap-3">
          <BrandMark className="size-10 bg-white/15 shadow-none" />
          <span className="text-lg font-semibold">Resume Optimizer</span>
        </div>
        <div className="relative flex flex-col gap-6">
          <h1 className="text-4xl leading-tight font-semibold tracking-tight">
            Walk into every application knowing where you stand.
          </h1>
          <ul className="flex flex-col gap-3 text-white/90">
            {POINTS.map((point) => (
              <li key={point} className="flex items-start gap-3">
                <CheckCircle2Icon className="mt-0.5 size-5 shrink-0" />
                {point}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-sm text-white/70">
          Built for students and new grads.
        </p>
      </section>

      <section className="flex flex-col items-center justify-center gap-4 px-4 py-12">
        <AuthError queryCode={typeof error === "string" ? error : null} />
        <LoginForm next={nextPath} />
      </section>
    </main>
  );
}
