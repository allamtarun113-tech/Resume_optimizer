// Hands a submitted analyze form to the /analysis/new page, which uploads the documents
// and starts the analysis while showing progress. Files can't go through a URL, so the
// payload lives in memory for the current tab (client-side navigation keeps it).

import { apiPostForm, apiPostJson } from "@/lib/api";
import {
  type ProjectEntry,
  filledProjects,
  formatProject,
} from "@/lib/projects";
import { buildExtraText } from "@/lib/skills";
import type {
  AnalysisCreate,
  AnalysisCreated,
  DocumentResponse,
} from "@/lib/types";

export type AnalyzePayload = {
  resume: File;
  jdText: string;
  skills: string[];
  about: string;
  projects: ProjectEntry[];
  supportingFiles: File[];
};

let pending: AnalyzePayload | null = null;
let inFlight: { payload: AnalyzePayload; promise: Promise<string> } | null =
  null;

export function setPendingAnalysis(payload: AnalyzePayload): void {
  pending = payload;
  inFlight = null;
}

export function getPendingAnalysis(): AnalyzePayload | null {
  return pending;
}

export function clearPendingAnalysis(): void {
  pending = null;
  inFlight = null;
}

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

async function submit(payload: AnalyzePayload): Promise<string> {
  const [resumeDoc, ...supportingDocs] = await Promise.all([
    uploadFile("resume", payload.resume),
    ...payload.supportingFiles.map((f) => uploadFile("supporting", f)),
    ...filledProjects(payload.projects).map((p) =>
      uploadText(formatProject(p)),
    ),
  ]);
  const body: AnalysisCreate = {
    resume_doc_id: resumeDoc.id,
    jd_text: payload.jdText,
    extra_text: buildExtraText(payload.skills, payload.about) || null,
    supporting_doc_ids: supportingDocs.map((d) => d.id),
  };
  const created = await apiPostJson<AnalysisCreated>("/analyses", body);
  return created.id;
}

// Starts the upload once per payload (React may run effects twice in development).
export function startPendingAnalysis(payload: AnalyzePayload): Promise<string> {
  if (inFlight?.payload !== payload) {
    const promise = submit(payload);
    inFlight = { payload, promise };
    // Allow a retry after a failure.
    promise.catch(() => {
      if (inFlight?.promise === promise) inFlight = null;
    });
  }
  return inFlight!.promise;
}
