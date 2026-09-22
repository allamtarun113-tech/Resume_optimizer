"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { apiPostForm, apiPostJson } from "@/lib/api";
import {
  MAX_EXTRA_CHARS,
  MAX_JD_CHARS,
  MAX_SUPPORTING_DOCS,
  RESUME_ACCEPT,
  SUPPORTING_ACCEPT,
  validateAnalyzeInput,
} from "@/lib/analyze";
import type {
  AnalysisCreate,
  AnalysisCreated,
  DocumentResponse,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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

export function AnalyzeForm() {
  const router = useRouter();
  const [resume, setResume] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [extraText, setExtraText] = useState("");
  const [supportingFiles, setSupportingFiles] = useState<File[]>([]);
  const [supportingText, setSupportingText] = useState("");
  const [step, setStep] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const input = {
      resume,
      jdText,
      extraText,
      supportingFiles,
      supportingText,
    };
    const problem = validateAnalyzeInput(input);
    if (problem) return toast.error(problem);

    try {
      setStep("Uploading and reading your documents…");
      const [resumeDoc, ...supportingDocs] = await Promise.all([
        uploadFile("resume", resume!),
        ...supportingFiles.map((f) => uploadFile("supporting", f)),
        ...(supportingText.trim() ? [uploadText(supportingText)] : []),
      ]);

      setStep("Starting analysis…");
      const body: AnalysisCreate = {
        resume_doc_id: resumeDoc.id,
        jd_text: jdText,
        extra_text: extraText.trim() || null,
        supporting_doc_ids: supportingDocs.map((d) => d.id),
      };
      const created = await apiPostJson<AnalysisCreated>("/analyses", body);
      router.push(`/analysis/${created.id}`);
    } catch (err) {
      toast.error((err as Error).message);
      setStep(null);
    }
  }

  const busy = step !== null;

  return (
    <form onSubmit={handleSubmit} className="flex w-full flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Resume and job</CardTitle>
          <CardDescription>
            Your resume must be a PDF or DOCX with selectable text (not a scan).
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="resume">Resume</Label>
            <Input
              id="resume"
              type="file"
              accept={RESUME_ACCEPT}
              disabled={busy}
              onChange={(e) => setResume(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="jd">Job description</Label>
            <Textarea
              id="jd"
              rows={10}
              maxLength={MAX_JD_CHARS}
              placeholder="Paste the full job description here."
              disabled={busy}
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {jdText.length.toLocaleString()} / {MAX_JD_CHARS.toLocaleString()}{" "}
              characters
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Anything missing from your resume?</CardTitle>
          <CardDescription>
            Optional. Projects, skills or experience you have but didn&apos;t
            put on your resume. We only suggest additions backed by what you
            give us here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="extra">Additional skills or experience</Label>
            <Textarea
              id="extra"
              rows={3}
              maxLength={MAX_EXTRA_CHARS}
              placeholder="e.g. Built a Kubernetes deployment for my food ordering app during a hackathon."
              disabled={busy}
              value={extraText}
              onChange={(e) => setExtraText(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="supporting">
              Supporting documents (up to {MAX_SUPPORTING_DOCS})
            </Label>
            <Input
              id="supporting"
              type="file"
              multiple
              accept={SUPPORTING_ACCEPT}
              disabled={busy}
              onChange={(e) =>
                setSupportingFiles(Array.from(e.target.files ?? []))
              }
            />
            <p className="text-xs text-muted-foreground">
              Project reports, older resumes, LinkedIn exports. PDF, DOCX or
              TXT, 5 MB each.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="supporting-text">
              Or paste a project description
            </Label>
            <Textarea
              id="supporting-text"
              rows={4}
              disabled={busy}
              value={supportingText}
              onChange={(e) => setSupportingText(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-4">
        <Button type="submit" disabled={busy}>
          {busy ? "Working…" : "Analyze"}
        </Button>
        {step && <p className="text-sm text-muted-foreground">{step}</p>}
      </div>
    </form>
  );
}
