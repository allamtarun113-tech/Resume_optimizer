"use client";

import { useState } from "react";
import { PlusIcon, XIcon } from "lucide-react";
import { MAX_SKILLS, MAX_SKILL_CHARS, addSkills } from "@/lib/skills";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// Type a skill and press Enter (or Add). Pasting "Docker, AWS" adds both.
export function SkillsInput({
  id,
  skills,
  onChange,
  disabled,
  placeholder = "e.g. Docker",
  addLabel = "Add skill",
}: {
  id: string;
  skills: string[];
  onChange: (skills: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  addLabel?: string;
}) {
  const [draft, setDraft] = useState("");

  function commit(raw: string) {
    const next = addSkills(skills, raw);
    if (next.length !== skills.length) onChange(next);
    setDraft("");
  }

  const full = skills.length >= MAX_SKILLS;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          maxLength={MAX_SKILL_CHARS * 4}
          placeholder={full ? `Up to ${MAX_SKILLS} skills` : placeholder}
          disabled={disabled || full}
          onChange={(e) => {
            const value = e.target.value;
            // Typing or pasting a comma turns what's before it into tags.
            if (/[,;\n]/.test(value)) commit(value);
            else setDraft(value);
          }}
          // A skill typed but not added yet still counts (e.g. clicking Analyze next).
          onBlur={() => {
            if (draft.trim()) commit(draft);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit(draft);
            } else if (e.key === "Backspace" && !draft && skills.length) {
              onChange(skills.slice(0, -1));
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={disabled || full || !draft.trim()}
          onClick={() => commit(draft)}
        >
          <PlusIcon />
          {addLabel}
        </Button>
      </div>
      {skills.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={`Added: ${id}`}>
          {skills.map((skill) => (
            <li
              key={skill.toLowerCase()}
              className="flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 py-1 pr-1 pl-3 text-sm font-medium text-primary"
            >
              {skill}
              <button
                type="button"
                aria-label={`Remove ${skill}`}
                disabled={disabled}
                className="rounded-full p-0.5 hover:bg-primary/15"
                onClick={() => onChange(skills.filter((s) => s !== skill))}
              >
                <XIcon className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
