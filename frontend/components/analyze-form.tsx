"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRightIcon,
  BriefcaseIcon,
  FileUserIcon,
  KeyRoundIcon,
  SparklesIcon,
} from "lucide-react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import type { AiSettings } from "@/lib/types";
import {
  MAX_SUPPORTING_DOCS,
  RESUME_ACCEPT,
  SUPPORTING_ACCEPT,
  MAX_ABOUT_CHARS,
  validateAnalyzeInput,
} from "@/lib/analyze";
import { emptyProject, filledProjects } from "@/lib/projects";
import { getPendingAnalysis, setPendingAnalysis } from "@/lib/pending-analysis";
import { FileDropzone } from "@/components/file-dropzone";
import { JobDescriptionInput } from "@/components/inputs/job-description-input";
import { ProjectList } from "@/components/inputs/project-descriptions";
import { SkillsInput } from "@/components/inputs/skills-input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

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
  // If starting the analysis failed, the previous entries are restored.
  const [draft] = useState(getPendingAnalysis);
  const [resume, setResume] = useState<File[]>(draft ? [draft.resume] : []);
  const [jdText, setJdText] = useState(draft?.jdText ?? "");
  const [skills, setSkills] = useState<string[]>(draft?.skills ?? []);
  const [about, setAbout] = useState(draft?.about ?? "");
  const [projects, setProjects] = useState(draft?.projects ?? [emptyProject()]);
  const [supportingFiles, setSupportingFiles] = useState<File[]>(
    draft?.supportingFiles ?? [],
  );

  useEffect(() => {
    apiFetch<AiSettings>("/settings/ai")
      .then((s) => setHasKey(s.has_key))
      .catch(() => setHasKey(true)); // don't block on a transient error; the API will say
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const input = {
      resume: resume[0] ?? null,
      jdText,
      skills,
      about,
      projects,
      supportingFiles,
    };
    const problem = validateAnalyzeInput(input);
    if (problem) return toast.error(problem);
    // Go straight to the results page; it uploads and shows progress from there.
    setPendingAnalysis({ ...input, resume: input.resume! });
    router.push("/analysis/new");
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
        />
      </Step>

      <Step
        number={2}
        icon={BriefcaseIcon}
        title="The job"
        description="Paste it, or upload the PDF/DOCX; you can edit the text either way."
      >
        <JobDescriptionInput value={jdText} onChange={setJdText} />
      </Step>

      <Step
        number={3}
        icon={SparklesIcon}
        title="Anything missing from your resume? (optional)"
        description="Skills, projects and documents you really have. Suggestions only ever use what you give here."
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor="skills">Additional skills</Label>
          <SkillsInput id="skills" skills={skills} onChange={setSkills} />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="about">About your skills & knowledge</Label>
          <Textarea
            id="about"
            rows={5}
            maxLength={MAX_ABOUT_CHARS}
            placeholder="In your own words: what you know and how you've used it. e.g. I'm comfortable with SQL joins and window functions from my DBMS course, and I've used Git daily in team projects."
            value={about}
            onChange={(e) => setAbout(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Plain English is fine. It&apos;s read alongside your resume, just
            like your other documents.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <Label>Projects</Label>
          <ProjectList
            projects={projects}
            onChange={setProjects}
            canAddMore={supportingCount < MAX_SUPPORTING_DOCS}
          />
        </div>
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
          />
        </div>
      </Step>

      <div className="sticky bottom-4 z-10 flex flex-col items-center gap-3 rounded-2xl border bg-background/90 p-4 shadow-lg backdrop-blur sm:flex-row sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Takes about a minute. You&apos;ll see the progress right away.
        </p>
        <Button type="submit" size="lg" className="w-full sm:w-auto">
          <SparklesIcon />
          Analyze
        </Button>
      </div>
    </form>
  );
}
