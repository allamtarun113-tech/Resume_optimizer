"use client";

import { FolderGit2Icon, PlusIcon, Trash2Icon } from "lucide-react";
import {
  MAX_PROJECT_DESCRIPTION,
  MAX_PROJECT_NAME,
  type ProjectEntry,
  emptyProject,
  isBlankProject,
} from "@/lib/projects";
import { SkillsInput } from "@/components/inputs/skills-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// One card per project: name, description, and the skills/frameworks used.
// Each filled project is sent as its own supporting document.
export function ProjectList({
  projects,
  onChange,
  canAddMore,
  disabled,
}: {
  projects: ProjectEntry[];
  onChange: (projects: ProjectEntry[]) => void;
  canAddMore: boolean;
  disabled?: boolean;
}) {
  const update = (index: number, patch: Partial<ProjectEntry>) =>
    onChange(projects.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  const remove = (index: number) =>
    onChange(
      projects.length === 1
        ? [emptyProject()]
        : projects.filter((_, i) => i !== index),
    );

  return (
    <div className="flex flex-col gap-4">
      {projects.map((project, i) => {
        const n = i + 1;
        return (
          <div
            key={i}
            className="flex flex-col gap-4 rounded-xl border bg-muted/30 p-4"
          >
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm font-semibold">
                <FolderGit2Icon className="size-4 text-primary" />
                Project {n}
              </span>
              {(projects.length > 1 || !isBlankProject(project)) && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={disabled}
                  className="text-muted-foreground"
                  onClick={() => remove(i)}
                >
                  <Trash2Icon />
                  Remove
                </Button>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`project-${n}-name`}>
                <span className="sr-only">Project {n} </span>Name
              </Label>
              <Input
                id={`project-${n}-name`}
                maxLength={MAX_PROJECT_NAME}
                placeholder="e.g. Campus Food Ordering App"
                disabled={disabled}
                value={project.name}
                onChange={(e) => update(i, { name: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`project-${n}-description`}>
                <span className="sr-only">Project {n} </span>Description
              </Label>
              <Textarea
                id={`project-${n}-description`}
                rows={4}
                maxLength={MAX_PROJECT_DESCRIPTION}
                placeholder="What you built and how, your role, and the results (numbers help)."
                disabled={disabled}
                value={project.description}
                onChange={(e) => update(i, { description: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`project-${n}-skills`}>
                <span className="sr-only">Project {n} </span>Skills & frameworks
                used
              </Label>
              <SkillsInput
                id={`project-${n}-skills`}
                skills={project.skills}
                onChange={(skills) => update(i, { skills })}
                disabled={disabled}
                placeholder="e.g. FastAPI"
                addLabel="Add"
              />
            </div>
          </div>
        );
      })}
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={disabled || !canAddMore}
          onClick={() => onChange([...projects, emptyProject()])}
        >
          <PlusIcon />
          Add another project
        </Button>
      </div>
    </div>
  );
}
