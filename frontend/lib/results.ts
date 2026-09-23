import type { AtsCheck, KeywordFact, RequirementMatch } from "@/lib/types";

export type Bucket = RequirementMatch["bucket"];

export const BUCKETS: {
  bucket: Bucket;
  title: string;
  description: string;
}[] = [
  {
    bucket: "strong_in_resume",
    title: "You're covered",
    description: "Your resume clearly shows these. Nothing to do.",
  },
  {
    bucket: "weak_in_resume",
    title: "Show these more clearly",
    description:
      "Your resume mentions these, but only in passing. Show where you used them.",
  },
  {
    bucket: "missing_from_resume_but_evidenced",
    title: "Add these to your resume",
    description:
      "You have them (we found them in your other documents or notes), but your resume doesn't say so.",
  },
  {
    bucket: "true_gap",
    title: "Still to learn",
    description:
      "Nothing you gave us shows these yet. Your learning path covers them.",
  },
];

export function groupMatches(
  matches: RequirementMatch[],
  skip: Bucket[] = [],
): {
  bucket: Bucket;
  title: string;
  description: string;
  items: RequirementMatch[];
}[] {
  return BUCKETS.filter((b) => !skip.includes(b.bucket))
    .map((b) => ({
      ...b,
      // Must-haves first, then heavier weights, then the job's original order.
      items: matches
        .filter((m) => m.bucket === b.bucket)
        .sort(
          (a, c) =>
            Number(c.importance === "must") - Number(a.importance === "must") ||
            c.weight - a.weight ||
            a.requirement_index - c.requirement_index,
        ),
    }))
    .filter((g) => g.items.length > 0);
}

export function scoreTone(score: number): "good" | "ok" | "low" {
  if (score >= 75) return "good";
  if (score >= 50) return "ok";
  return "low";
}

export const SECTION_LABEL: Record<string, string> = {
  skills: "Skills",
  projects: "Projects",
  experience: "Experience",
  education: "Education",
  certifications: "Certifications",
  summary: "Summary",
};

export function whereToAdd(section: string, target: string | null): string {
  const label = SECTION_LABEL[section] ?? section;
  return target ? `${label} → ${target}` : label;
}

export function formatHours(hours: number | null | undefined): string | null {
  if (hours == null || hours <= 0) return null;
  if (hours < 1) return "under 1 hour";
  const rounded = Math.round(hours);
  return `about ${rounded} hour${rounded === 1 ? "" : "s"}`;
}

type SourcedQuestion = {
  topic?: string | null;
  source: {
    kind: string;
    label: string;
    url?: string | null;
    license?: string | null;
  };
};

// Technical questions grouped by the job requirement they were retrieved for.
export function groupByTopic<T extends SourcedQuestion>(
  questions: T[],
): { topic: string; questions: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const q of questions) {
    const key = q.topic ?? "Other";
    groups.set(key, [...(groups.get(key) ?? []), q]);
  }
  return [...groups].map(([topic, qs]) => ({ topic, questions: qs }));
}

export function sourceText(source: SourcedQuestion["source"]): string {
  if (source.kind === "template") return "Project deep-dive template";
  return source.license ? `${source.label} (${source.license})` : source.label;
}

// -- plain-English wording for the results page --------------------------------------

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function scoreVerdict(score: number): string {
  if (score >= 75) return "Strong match";
  if (score >= 50) return "Good start";
  return "Needs work";
}

export function scoreSentence(fit: number, potential: number | null): string {
  const base = `Your resume shows ${fit}% of what this job asks for.`;
  return potential != null && potential > fit
    ? `${base} Adding things you already have (from your other documents and notes) could raise it to ${potential}%.`
    : base;
}

// Explains the "after adding what you have" score next to the resume score.
export function afterAddingText(fit: number, potential: number): string {
  if (potential > fit)
    return `Add the lines below to your resume and your score goes from ${fit}% to ${potential}% (+${potential - fit} points), using only things you already have.`;
  return `Your other documents and notes don't show anything more that this job asks for, so adding them wouldn't change the score (${fit}%). Upload project reports or describe work that isn't on your resume to find more.`;
}

type Evidence = RequirementMatch["evidence"][number];

const DEMONSTRATED = ["project", "experience"];

function isDemonstrated(e: Evidence): boolean {
  return DEMONSTRATED.includes(e.kind) || DEMONSTRATED.includes(e.context);
}

function years(n: number): string {
  const rounded = Math.round(n * 10) / 10;
  return `${rounded} year${rounded === 1 ? "" : "s"}`;
}

// One sentence a student can act on: what we found and what it means.
export function plainStatus(m: RequirementMatch): string {
  const onResume = m.evidence.filter((e) => e.direct && e.source === "resume");
  const used = onResume.find(isDemonstrated);
  const listed = onResume.some((e) => !isDemonstrated(e));
  const yearsNote =
    m.min_years != null
      ? ` The job asks for ${years(m.min_years)}; your resume shows about ${years(m.resume_years ?? 0)}.`
      : "";

  switch (m.bucket) {
    case "strong_in_resume":
      return (
        (used
          ? `On your resume, and you show it in ${used.label}.`
          : "Clearly shown on your resume.") + yearsNote
      );
    case "weak_in_resume": {
      const why =
        m.min_years != null
          ? "On your resume, but with less experience than the job asks for."
          : listed && !used
            ? "Listed on your resume, but no project or job there shows you using it."
            : used && !listed
              ? `You used it in ${used.label}, but your resume doesn't name it clearly.`
              : "Only hinted at on your resume, not stated clearly.";
      const more =
        m.best_strength > m.resume_strength
          ? " Your other documents show more: see Improve resume."
          : "";
      return why + yearsNote + more;
    }
    case "missing_from_resume_but_evidenced":
      return "Not on your resume, but your other documents or notes show it. Adding it raises your score.";
    case "true_gap":
      return m.category === "skill" || m.category === "domain"
        ? "Not found in anything you gave us yet. It's in your learning path."
        : "Not found in anything you gave us yet.";
  }
}

export function evidenceWhere(e: Evidence): string {
  const where =
    e.source === "resume" ? "your resume" : "your other documents or notes";
  const what =
    e.kind === "skill"
      ? e.context === "skills_section"
        ? "skills list"
        : e.context.replace("_", " ")
      : e.kind;
  return `${what} in ${where}${e.direct ? "" : " (related, not exact)"}`;
}

// The one number shown first: the final score (job fit + ATS), or job fit on analyses
// made before the ATS check existed.
export function headlineScore(item: {
  final_score: number | null;
  fit_score: number | null;
}): number | null {
  return item.final_score ?? item.fit_score;
}

export function atsSentence(ats: number): string {
  return `Hiring software (an ATS) can read it and find the job's keywords at ${ats}%.`;
}

export const ATS_GROUP_TITLE: Record<AtsCheck["group"], string> = {
  readable: "Can hiring software read it?",
  sections: "Sections and contact details",
  keywords: "The job's keywords",
};

export function atsIssues(checks: AtsCheck[]): AtsCheck[] {
  return checks.filter((c) => c.status !== "pass");
}

// Where to go for a keyword the resume doesn't use yet.
export function keywordHint(bucket: KeywordFact["bucket"]): string {
  switch (bucket) {
    case "strong_in_resume":
    case "weak_in_resume":
      return "You show this, but not with the job's exact word. Use the job's wording.";
    case "missing_from_resume_but_evidenced":
      return "You have this in your other documents: add it (see Improve resume).";
    case "true_gap":
      return "Not shown anywhere yet: see Learn.";
    default:
      return "Not written in your resume.";
  }
}

export type NextStep = {
  title: string;
  detail: string;
  tab: "improve" | "ats" | "learn" | "interview";
};

export function nextSteps(input: {
  fitScore: number | null;
  potentialScore: number | null;
  suggestionCount: number;
  gapNames: string[];
  atsIssues?: number;
  atsScore?: number | null;
}): NextStep[] {
  const steps: NextStep[] = [];
  if (input.atsIssues) {
    steps.push({
      title: `Fix ${plural(input.atsIssues, "thing")} that hiring software may trip over`,
      detail: `Your ATS score is ${input.atsScore}%. Each fix is a small change to your resume file.`,
      tab: "ats",
    });
  }
  if (input.suggestionCount > 0) {
    steps.push({
      title: `Add ${plural(input.suggestionCount, "thing")} you already have to your resume`,
      detail:
        input.potentialScore != null && input.fitScore != null
          ? `Ready-to-copy lines, based only on what you gave us. Could take you from ${input.fitScore}% to ${input.potentialScore}%.`
          : "Ready-to-copy lines, based only on what you gave us.",
      tab: "improve",
    });
  }
  if (input.gapNames.length > 0) {
    const shown = input.gapNames.slice(0, 3).join(", ");
    const more =
      input.gapNames.length > 3 ? ` and ${input.gapNames.length - 3} more` : "";
    steps.push({
      title: `Learn what's missing: ${shown}${more}`,
      detail: "A step-by-step plan with free resources, basics first.",
      tab: "learn",
    });
  }
  steps.push({
    title: "Practise for the interview",
    detail:
      "Real questions for this job and deep questions about your projects.",
    tab: "interview",
  });
  return steps;
}

export function isYouTube(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return (
      host === "youtu.be" ||
      host === "youtube.com" ||
      host.endsWith(".youtube.com")
    );
  } catch {
    return false;
  }
}

// A YouTube search (built here, never by the AI) for more videos on a topic.
export function youTubeSearchUrl(topic: string): string {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(`${topic} tutorial`)}`;
}
