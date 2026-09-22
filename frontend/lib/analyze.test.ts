import { describe, expect, it } from "vitest";
import {
  MAX_FILE_BYTES,
  validateAnalyzeInput,
  type AnalyzeInput,
} from "./analyze";

const file = (name: string, size = 1000) => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "size", { value: size });
  return f;
};

const valid: AnalyzeInput = {
  resume: file("resume.pdf"),
  jdText:
    "Backend engineer. Requirements: Python, FastAPI, PostgreSQL, Docker.",
  extraText: "",
  supportingFiles: [],
  supportingText: "",
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

  it("limits supporting documents, counting pasted text as one", () => {
    const five = Array.from({ length: 5 }, (_, i) => file(`p${i}.pdf`));
    expect(
      validateAnalyzeInput({ ...valid, supportingFiles: five }),
    ).toBeNull();
    expect(
      validateAnalyzeInput({
        ...valid,
        supportingFiles: five,
        supportingText: "more",
      }),
    ).toMatch(/at most 5/);
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
