import { AnalyzeForm } from "@/components/analyze-form";

export default function AnalyzePage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-10">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">New analysis</h1>
        <p className="text-muted-foreground">
          Upload your resume and paste the job you want. We&apos;ll score your
          fit, suggest honest improvements, plan what to learn and prepare you
          for the interview.
        </p>
      </div>
      <AnalyzeForm />
    </main>
  );
}
