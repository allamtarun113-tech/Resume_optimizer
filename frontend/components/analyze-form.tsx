"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRightIcon,
  BriefcaseIcon,
  FileUserIcon,
  KeyRoundIcon,
  Loader2Icon,
  SparklesIcon,
} from "lucide-react";
import { toast } from "sonner";
import { apiFetch, apiPostForm, apiPostJson } from "@/lib/api";
import {
  MAX_SUPPORTING_DOCS,
  RESUME_ACCEPT,
  SUPPORTING_ACCEPT,
  filledProjects,
  validateAnalyzeInput,
} from "@/lib/analyze";
import { formatSkills } from "@/lib/skills";
import { showApiError } from "@/lib/errors";
import type {
  AiSettings,
  AnalysisCreate,
  AnalysisCreated,
  DocumentResponse,
} from "@/lib/types";
import { FileDropzone } from "@/components/file-dropzone";
import { JobDescriptionInput } from "@/components/inputs/job-description-input";
import { ProjectDescriptions } from "@/components/inputs/project-descriptions";
import { SkillsInput } from "@/components/inputs/skills-input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

function uploadFile(kind: "resume" | "supporting", file: File) {
  const form = new FormData();
  form.set("kind", kind);
  form.set("file", file);
  return apiPostForm<DocumentResponse>("/documents", form);
}

function uploadText(text: string) {
  const form = new FormData();
  form.set("kind", "supporting");
  form.set("text", text);
  return apiPostForm<DocumentResponse>("/documents", form);
}

function Step({
  number,
  icon: Icon,
  title,
  description,
  children,
}: {
  number: number;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border bg-card p-5 shadow-sm sm:p-6">
      <div className="mb-5 flex items-start gap-4">
        <span className="relative flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Icon className="size-5" />
          <span className="bg-brand-gradient absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full text-[10px] font-bold text-white">
            {number}
          </span>
        </span>
        <div>
          <h2 className="font-semibold">{title}</h2>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </section>
  );
}

export function AnalyzeForm() {
  const router = useRouter();
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [resume, setResume] = useState<File[]>([]);
  const [jdText, setJdText] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([""]);
  const [supportingFiles, setSupportingFiles] = useState<File[]>([]);
  const [step, setStep] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AiSettings>("/settings/ai")
      .then((s) => setHasKey(s.has_key))
      .catch(() => setHasKey(true)); // don't block on a transient error; the API will say
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const input = {
      resume: resume[0] ?? null,
      jdText,
      skills,
      projects,
      supportingFiles,
    };
    const problem = validateAnalyzeInput(input);
    if (problem) return toast.error(problem);

    try {
      setStep("Uploading and reading your documents…");
      const [resumeDoc, ...supportingDocs] = await Promise.all([
        uploadFile("resume", input.resume!),
        ...supportingFiles.map((f) => uploadFile("supporting", f)),
        ...filledProjects(projects).map(uploadText),
      ]);

      setStep("Starting analysis…");
      const body: AnalysisCreate = {
        resume_doc_id: resumeDoc.id,
        jd_text: jdText,
        extra_text: formatSkills(skills) || null,
        supporting_doc_ids: supportingDocs.map((d) => d.id),
      };
      const created = await apiPostJson<AnalysisCreated>("/analyses", body);
      router.push(`/analysis/${created.id}`);
    } catch (err) {
      showApiError(err, router.push);
      setStep(null);
    }
  }

  if (hasKey === null) return <Skeleton className="h-96 w-full rounded-2xl" />;

  if (!hasKey) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl border bg-card px-6 py-12 text-center shadow-sm">
        <span className="bg-brand-gradient flex size-14 items-center justify-center rounded-2xl text-white shadow-lg shadow-primary/25">
          <KeyRoundIcon className="size-6" />
        </span>
        <h2 className="text-xl font-semibold">Add your OpenAI key first</h2>
        <p className="max-w-md text-muted-foreground">
          Analyses run on your own OpenAI account (about $0.002 each). Add your
          API key and choose a model, then come back here.
        </p>
        <Button
          size="lg"
          nativeButton={false}
          render={<Link href="/settings" />}
        >
          Go to Settings
          <ArrowRightIcon />
        </Button>
      </div>
    );
  }

  const busy = step !== null;
  const supportingCount =
    supportingFiles.length + filledProjects(projects).length;

  return (
    <form onSubmit={handleSubmit} className="flex w-full flex-col gap-6">
      <Step
        number={1}
        icon={FileUserIcon}
        title="Your resume"
        description="PDF or DOCX with selectable text (not a scan), up to 5 MB."
      >
        <FileDropzone
          label="Drop your resume here, or click to choose"
          hint="PDF or DOCX"
          accept={RESUME_ACCEPT}
          files={resume}
          onChange={setResume}
          disabled={busy}
        />
      </Step>

      <Step
        number={2}
        icon={BriefcaseIcon}
        title="The job"
        description="Paste it, or upload the PDF/DOCX; you can edit the text either way."
      >
        <JobDescriptionInput
          value={jdText}
          onChange={setJdText}
          disabled={busy}
        />
      </Step>

      <Step
        number={3}
        icon={SparklesIcon}
        title="Anything missing from your resume? (optional)"
        description="Skills, projects and documents you really have. Suggestions only ever use what you give here."
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor="skills">Additional skills</Label>
          <SkillsInput
            id="skills"
            skills={skills}
            onChange={setSkills}
            disabled={busy}
          />
        </div>
        <ProjectDescriptions
          projects={projects}
          onChange={setProjects}
          canAddMore={supportingCount < MAX_SUPPORTING_DOCS}
          disabled={busy}
        />
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <Label>Supporting documents</Label>
            <span className="text-xs text-muted-foreground tabular-nums">
              {supportingCount} / {MAX_SUPPORTING_DOCS} documents and projects
            </span>
          </div>
          <FileDropzone
            label="Drop project reports, older resumes or exports"
            hint="PDF, DOCX or TXT · 5 MB each"
            accept={SUPPORTING_ACCEPT}
            multiple
            files={supportingFiles}
            onChange={setSupportingFiles}
            disabled={busy}
          />
        </div>
      </Step>

      <div className="sticky bottom-4 z-10 flex flex-col items-center gap-3 rounded-2xl border bg-background/90 p-4 shadow-lg backdrop-blur sm:flex-row sm:justify-between">
        <p className="text-sm text-muted-foreground">
          {step ?? "Takes about a minute. You can leave the results page open."}
        </p>
        <Button
          type="submit"
          size="lg"
          disabled={busy}
          className="w-full sm:w-auto"
        >
          {busy ? <Loader2Icon className="animate-spin" /> : <SparklesIcon />}
          {busy ? "Working…" : "Analyze"}
        </Button>
      </div>
    </form>
  );
}
