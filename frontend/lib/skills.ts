// Skill tags typed by the student ("Add skill"). Sent to the backend as one line of
// extra text, which the profile extractor reads like any other supporting note.

export const MAX_SKILLS = 50;
export const MAX_SKILL_CHARS = 60;

// Adds one or more skills ("Docker, AWS; Redis" adds three). Trims, collapses spaces,
// drops empties and case-insensitive duplicates, and caps length and count.
export function addSkills(current: string[], raw: string): string[] {
  const seen = new Set(current.map((s) => s.toLowerCase()));
  const next = [...current];
  for (const part of raw.split(/[,;\n]/)) {
    const skill = part.replace(/\s+/g, " ").trim().slice(0, MAX_SKILL_CHARS);
    if (!skill || seen.has(skill.toLowerCase()) || next.length >= MAX_SKILLS)
      continue;
    seen.add(skill.toLowerCase());
    next.push(skill);
  }
  return next;
}

export function formatSkills(skills: string[]): string {
  return skills.length ? `Additional skills: ${skills.join(", ")}.` : "";
}

// Everything from "Anything missing from your resume?" that isn't a document:
// skill tags plus the student's own plain-English description of what they know.
export function buildExtraText(skills: string[], about: string): string {
  const parts = [formatSkills(skills)];
  if (about.trim())
    parts.push(`About my skills and knowledge:\n${about.trim()}`);
  return parts.filter(Boolean).join("\n\n");
}
