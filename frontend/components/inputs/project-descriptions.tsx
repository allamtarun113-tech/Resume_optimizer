"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";
import { MAX_PROJECT_CHARS } from "@/lib/analyze";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// A growing list of pasted project descriptions; each becomes its own supporting document.
export function ProjectDescriptions({
  projects,
  onChange,
  canAddMore,
  disabled,
}: {
  projects: string[];
  onChange: (projects: string[]) => void;
  canAddMore: boolean;
  disabled?: boolean;
}) {
  const update = (index: number, value: string) =>
    onChange(projects.map((p, i) => (i === index ? value : p)));
  const remove = (index: number) =>
    onChange(
      projects.length === 1 ? [""] : projects.filter((_, i) => i !== index),
    );

  return (
    <div className="flex flex-col gap-4">
      {projects.map((text, i) => {
        const id = `project-${i + 1}`;
        return (
          <div key={i} className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor={id}>Project description {i + 1}</Label>
              {(projects.length > 1 || text) && (
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
            <Textarea
              id={id}
              rows={4}
              maxLength={MAX_PROJECT_CHARS}
              placeholder="What you built, the tech you used, your role and results."
              disabled={disabled}
              value={text}
              onChange={(e) => update(i, e.target.value)}
            />
          </div>
        );
      })}
      <div>
        <Button
          type="button"
          variant="outline"
          disabled={disabled || !canAddMore}
          onClick={() => onChange([...projects, ""])}
        >
          <PlusIcon />
          Add project description
        </Button>
      </div>
    </div>
  );
}
