// Client-side checks that mirror the backend limits (backend/app/schemas/analyses.py,
// backend/app/api/documents.py). The backend re-validates everything.

export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const MIN_JD_CHARS = 50;
export const MAX_JD_CHARS = 15_000;
export const MAX_EXTRA_CHARS = 5_000;
export const MAX_SUPPORTING_DOCS = 5;

export const RESUME_ACCEPT = ".pdf,.docx";
export const SUPPORTING_ACCEPT = ".pdf,.docx,.txt,.md";

export type AnalyzeInput = {
  resume: File | null;
  jdText: string;
  extraText: string;
  supportingFiles: File[];
  supportingText: string;
};

function extension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

export function validateAnalyzeInput(input: AnalyzeInput): string | null {
  if (!input.resume) return "Choose your resume (PDF or DOCX).";
  if (!RESUME_ACCEPT.split(",").includes(extension(input.resume.name)))
    return "The resume must be a PDF or DOCX file.";

  const jd = input.jdText.trim();
  if (jd.length < MIN_JD_CHARS)
    return `Paste the full job description (at least ${MIN_JD_CHARS} characters).`;
  if (jd.length > MAX_JD_CHARS)
    return `The job description is too long (max ${MAX_JD_CHARS.toLocaleString()} characters).`;
  if (input.extraText.length > MAX_EXTRA_CHARS)
    return `Additional skills must be under ${MAX_EXTRA_CHARS.toLocaleString()} characters.`;

  const supportingCount =
    input.supportingFiles.length + (input.supportingText.trim() ? 1 : 0);
  if (supportingCount > MAX_SUPPORTING_DOCS)
    return `Add at most ${MAX_SUPPORTING_DOCS} supporting documents (pasted text counts as one).`;

  const allowed = SUPPORTING_ACCEPT.split(",");
  const badType = input.supportingFiles.find(
    (f) => !allowed.includes(extension(f.name)),
  );
  if (badType) return `${badType.name}: use PDF, DOCX or TXT.`;

  const tooBig = [input.resume, ...input.supportingFiles].find(
    (f) => f.size > MAX_FILE_BYTES,
  );
  if (tooBig) return `${tooBig.name} is larger than 5 MB.`;
  return null;
}
