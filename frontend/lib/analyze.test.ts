import { describe, expect, it } from "vitest";
import {
  MAX_FILE_BYTES,
  validateAnalyzeInput,
  type AnalyzeInput,
} from "./analyze";
import { emptyProject, type ProjectEntry } from "./projects";

const project = (name: string): ProjectEntry => ({
  name,
  description: `${name} description`,
  skills: [],
});

const file = (name: string, size = 1000) => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
};

const valid: AnalyzeInput = {
  resume: file("resume.pdf"),
  jdText:
    "Backend engineer. Requirements: Python, FastAPI, PostgreSQL, Docker.",
  skills: [],
  about: "",
  projects: [emptyProject()],
  supportingFiles: [],
};

describe("validateAnalyzeInput", () => {
  it("accepts a valid submission", () => {
    expect(validateAnalyzeInput(valid)).toBeNull();
    expect(
      validateAnalyzeInput({ ...valid, resume: file("CV.DOCX") }),
    ).toBeNull();
  });

  it("requires a PDF or DOCX resume", () => {
    expect(validateAnalyzeInput({ ...valid, resume: null })).toMatch(/resume/);
    expect(
      validateAnalyzeInput({ ...valid, resume: file("resume.txt") }),
    ).toMatch(/PDF or DOCX/);
  });

  it("checks job description length", () => {
    expect(validateAnalyzeInput({ ...valid, jdText: "  short  " })).toMatch(
      /at least 50/,
    );
    expect(
      validateAnalyzeInput({ ...valid, jdText: "x".repeat(15_001) }),
    ).toMatch(/too long/);
  });

  it("allows up to 20 files and project descriptions together", () => {
    const files = Array.from({ length: 18 }, (_, i) => file(`p${i}.pdf`));
    const projects = [project("A"), project("B"), emptyProject()];
    expect(
      validateAnalyzeInput({ ...valid, supportingFiles: files, projects }),
    ).toBeNull();
    expect(
      validateAnalyzeInput({
        ...valid,
        supportingFiles: files,
        projects: [...projects, project("C")],
      }),
    ).toMatch(/at most 20 .* \(you have 21\)/);
  });

  it("validates projects and the about text", () => {
    expect(
      validateAnalyzeInput({
        ...valid,
        projects: [{ name: "", description: "x", skills: [] }],
      }),
    ).toMatch(/Project 1: add a project name/);
    expect(
      validateAnalyzeInput({ ...valid, about: "x".repeat(8_001) }),
    ).toMatch(/About your skills/);
  });

  it("rejects unsupported types and large files", () => {
    expect(
      validateAnalyzeInput({ ...valid, supportingFiles: [file("pic.png")] }),
    ).toMatch(/pic.png/);
    expect(
      validateAnalyzeInput({
        ...valid,
        resume: file("resume.pdf", MAX_FILE_BYTES + 1),
      }),
    ).toMatch(/larger than 5 MB/);
  });
});
