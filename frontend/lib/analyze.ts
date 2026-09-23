// Client-side checks that mirror the backend limits (backend/app/schemas/analyses.py,
// backend/app/api/documents.py). The backend re-validates everything.

import {
  type ProjectEntry,
  filledProjects,
  projectProblem,
} from "@/lib/projects";
import { buildExtraText } from "@/lib/skills";

export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const MIN_JD_CHARS = 50;
export const MAX_JD_CHARS = 15_000;
export const MAX_EXTRA_CHARS = 10_000; // skill tags + "about my skills" text
export const MAX_ABOUT_CHARS = 8_000;
export const MAX_SUPPORTING_DOCS = 20;

export const RESUME_ACCEPT = ".pdf,.docx";
export const SUPPORTING_ACCEPT = ".pdf,.docx,.txt,.md";
export const JD_ACCEPT = ".pdf,.docx,.txt,.md";

export type AnalyzeInput = {
  resume: File | null;
  jdText: string;
  skills: string[];
  about: string;
  projects: ProjectEntry[];
  supportingFiles: File[];
};

function extension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

export function hasAllowedExtension(name: string, accept: string): boolean {
  return accept.split(",").includes(extension(name));
}

export function validateAnalyzeInput(input: AnalyzeInput): string | null {
  if (!input.resume) return "Choose your resume (PDF or DOCX).";
  if (!hasAllowedExtension(input.resume.name, RESUME_ACCEPT))
    return "The resume must be a PDF or DOCX file.";

  const jd = input.jdText.trim();
  if (jd.length < MIN_JD_CHARS)
    return `Add the full job description (at least ${MIN_JD_CHARS} characters).`;
  if (jd.length > MAX_JD_CHARS)
    return `The job description is too long (max ${MAX_JD_CHARS.toLocaleString()} characters).`;
  if (input.about.length > MAX_ABOUT_CHARS)
    return `"About your skills" can be up to ${MAX_ABOUT_CHARS.toLocaleString()} characters.`;
  if (buildExtraText(input.skills, input.about).length > MAX_EXTRA_CHARS)
    return "That's a lot of skills. Please remove a few.";

  const problem = projectProblem(input.projects);
  if (problem) return problem;
  const projects = filledProjects(input.projects);

  const supportingCount = input.supportingFiles.length + projects.length;
  if (supportingCount > MAX_SUPPORTING_DOCS)
    return `Add at most ${MAX_SUPPORTING_DOCS} supporting documents and project descriptions in total (you have ${supportingCount}).`;

  const badType = input.supportingFiles.find(
    (f) => !hasAllowedExtension(f.name, SUPPORTING_ACCEPT),
  );
  if (badType) return `${badType.name}: use PDF, DOCX or TXT.`;

  const tooBig = [input.resume, ...input.supportingFiles].find(
    (f) => f.size > MAX_FILE_BYTES,
  );
  if (tooBig) return `${tooBig.name} is larger than 5 MB.`;
  return null;
}
