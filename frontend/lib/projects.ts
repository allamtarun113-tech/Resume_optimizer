// Structured project entries on the analyze form. Each filled project is uploaded as its
// own supporting document, in a labelled plain-text layout the profile extractor reads.

export type ProjectEntry = {
  name: string;
  description: string;
  skills: string[];
};

export const MAX_PROJECT_NAME = 120;
export const MAX_PROJECT_DESCRIPTION = 20_000;

export const emptyProject = (): ProjectEntry => ({
  name: "",
  description: "",
  skills: [],
});

export function isBlankProject(p: ProjectEntry): boolean {
  return !p.name.trim() && !p.description.trim() && p.skills.length === 0;
}

export function filledProjects(projects: ProjectEntry[]): ProjectEntry[] {
  return projects.filter((p) => !isBlankProject(p));
}

export function formatProject(p: ProjectEntry): string {
  const lines = [`Project: ${p.name.trim()}`];
  if (p.skills.length)
    lines.push(`Skills and frameworks used: ${p.skills.join(", ")}`);
  if (p.description.trim())
    lines.push("", "Description:", p.description.trim());
  return lines.join("\n");
}

// Returns a message for the first incomplete project, or null.
export function projectProblem(projects: ProjectEntry[]): string | null {
  for (const [i, p] of projects.entries()) {
    if (isBlankProject(p)) continue;
    const label = `Project ${i + 1}`;
    if (!p.name.trim()) return `${label}: add a project name.`;
    if (!p.description.trim() && p.skills.length === 0)
      return `${label}: add a description or the skills and frameworks you used.`;
    if (p.description.length > MAX_PROJECT_DESCRIPTION)
      return `${label}: the description can be up to ${MAX_PROJECT_DESCRIPTION.toLocaleString()} characters.`;
  }
  return null;
}
