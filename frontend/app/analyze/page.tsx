import { AnalyzeForm } from "@/components/analyze-form";

export default function AnalyzePage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-4 py-10">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">New analysis</h1>
        <p className="text-muted-foreground">
          Upload your resume and paste the job you want. We&apos;ll extract your
          skills and the job&apos;s requirements.
        </p>
      </div>
      <AnalyzeForm />
    </main>
  );
}
