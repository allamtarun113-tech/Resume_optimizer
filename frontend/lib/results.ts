import type { RequirementMatch } from "@/lib/types";

export type Bucket = RequirementMatch["bucket"];

export const BUCKETS: {
  bucket: Bucket;
  title: string;
  description: string;
}[] = [
  {
    bucket: "strong_in_resume",
    title: "Strong matches",
    description: "Listed on your resume and backed by a project or job.",
  },
  {
    bucket: "weak_in_resume",
    title: "Weak on your resume",
    description:
      "Your resume mentions it, but only in passing (listed without a project, or only implied).",
  },
  {
    bucket: "missing_from_resume_but_evidenced",
    title: "You have it, but it's not on your resume",
    description:
      "Found in your other documents or notes. Adding it to your resume raises your score.",
  },
  {
    bucket: "true_gap",
    title: "Skill gaps",
    description: "No evidence anywhere yet. These are what to learn next.",
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

export function strengthLabel(strength: number): string {
  if (strength >= 1) return "Strong";
  if (strength >= 0.7) return "Listed";
  if (strength > 0) return "Partial";
  return "Missing";
}

export function scoreTone(score: number): "good" | "ok" | "low" {
  if (score >= 75) return "good";
  if (score >= 50) return "ok";
  return "low";
}

export function sourceLabel(source: string): string {
  return source === "resume" ? "resume" : "other docs";
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
