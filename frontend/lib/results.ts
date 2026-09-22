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

export function groupMatches(matches: RequirementMatch[]): {
  bucket: Bucket;
  title: string;
  description: string;
  items: RequirementMatch[];
}[] {
  return BUCKETS.map((b) => ({
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
  })).filter((g) => g.items.length > 0);
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
