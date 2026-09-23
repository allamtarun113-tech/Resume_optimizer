"use client";

import { useId, useRef, useState } from "react";
import { FileTextIcon, Loader2Icon, UploadIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { apiPostForm } from "@/lib/api";
import { JD_ACCEPT, MAX_JD_CHARS, hasAllowedExtension } from "@/lib/analyze";
import type { ExtractedText } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// Paste the job description, or upload a PDF/DOCX/TXT to fill the box with its text
// (which can then be reviewed and edited). Files can also be dropped onto the box.
export function JobDescriptionInput({
  value,
  onChange,
  disabled,
  rows = 10,
  label = "Job description",
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  rows?: number;
  label?: string;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<string | null>(null);

  async function load(file: File | undefined) {
    if (!file) return;
    if (!hasAllowedExtension(file.name, JD_ACCEPT))
      return toast.error("Upload the job description as PDF, DOCX or TXT.");
    setLoading(true);
    try {
      const form = new FormData();
      form.set("file", file);
      const result = await apiPostForm<ExtractedText>(
        "/documents/extract-text",
        form,
      );
      onChange(result.text);
      setSource(file.name);
      toast.success(
        `Loaded text from ${file.name}. Check it and edit if needed.`,
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || loading}
          onClick={() => input.current?.click()}
        >
          {loading ? <Loader2Icon className="animate-spin" /> : <UploadIcon />}
          Upload PDF, DOCX or TXT
        </Button>
        <input
          ref={input}
          type="file"
          accept={JD_ACCEPT}
          className="sr-only"
          aria-label="Upload job description file"
          tabIndex={-1}
          onChange={(e) => {
            load(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      <Textarea
        id={id}
        rows={rows}
        maxLength={MAX_JD_CHARS}
        placeholder="Paste the full job description here, or upload it as a file."
        disabled={disabled || loading}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          if (!e.target.value) setSource(null);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          if (e.dataTransfer.files.length) {
            e.preventDefault();
            load(e.dataTransfer.files[0]);
          }
        }}
      />
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        {source ? (
          <span className="flex min-w-0 items-center gap-1.5">
            <FileTextIcon className="size-3.5 shrink-0 text-primary" />
            <span className="truncate">Loaded from {source}</span>
            <button
              type="button"
              aria-label="Clear job description"
              className="rounded p-0.5 hover:bg-muted"
              onClick={() => {
                onChange("");
                setSource(null);
              }}
            >
              <XIcon className="size-3.5" />
            </button>
          </span>
        ) : (
          <span>Tip: you can also drop a file onto the box.</span>
        )}
        <span className="shrink-0 tabular-nums">
          {value.length.toLocaleString()} / {MAX_JD_CHARS.toLocaleString()}
        </span>
      </div>
    </div>
  );
}
