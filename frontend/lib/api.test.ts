import { describe, expect, it } from "vitest";
import { errorMessage } from "./api";

describe("errorMessage", () => {
  it("returns string details as-is", () => {
    expect(errorMessage("Resume not found.", "x")).toBe("Resume not found.");
  });

  it("joins FastAPI validation errors", () => {
    const detail = [
      {
        loc: ["body", "jd_text"],
        msg: "String should have at least 50 characters",
      },
      { loc: ["body", "resume_doc_id"], msg: "Input should be a valid UUID" },
    ];
    expect(errorMessage(detail, "x")).toBe(
      "String should have at least 50 characters; Input should be a valid UUID",
    );
  });

  it("falls back for anything else", () => {
    expect(errorMessage(undefined, "Request failed")).toBe("Request failed");
    expect(errorMessage([{ nope: 1 }], "Request failed")).toBe(
      "Request failed",
    );
  });
});
