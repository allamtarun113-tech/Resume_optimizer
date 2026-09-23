import { beforeEach, describe, expect, it, vi } from "vitest";

const apiPostForm = vi.fn();
const apiPostJson = vi.fn();
vi.mock("@/lib/api", () => ({ apiPostForm, apiPostJson }));

const {
  clearPendingAnalysis,
  getPendingAnalysis,
  setPendingAnalysis,
  startPendingAnalysis,
} = await import("@/lib/pending-analysis");

const payload = () => ({
  resume: new File(["pdf"], "cv.pdf"),
  jdText: "We need Python.",
  skills: ["Git"],
  about: "I know Docker.",
  projects: [{ name: "App", description: "Built it", skills: ["React"] }],
  supportingFiles: [new File(["x"], "extra.pdf")],
});

describe("pending analysis", () => {
  beforeEach(() => {
    clearPendingAnalysis();
    apiPostForm.mockReset();
    apiPostJson.mockReset();
    let n = 0;
    apiPostForm.mockImplementation(async () => ({ id: `doc-${++n}` }));
    apiPostJson.mockResolvedValue({ id: "analysis-1" });
  });

  it("keeps the payload until cleared", () => {
    const p = payload();
    setPendingAnalysis(p);
    expect(getPendingAnalysis()).toBe(p);
    clearPendingAnalysis();
    expect(getPendingAnalysis()).toBeNull();
  });

  it("uploads everything once and starts the analysis", async () => {
    const p = payload();
    setPendingAnalysis(p);
    const [a, b] = [startPendingAnalysis(p), startPendingAnalysis(p)];
    expect(await a).toBe("analysis-1");
    expect(await b).toBe("analysis-1");
    expect(apiPostForm).toHaveBeenCalledTimes(3); // resume, file, project
    expect(apiPostJson).toHaveBeenCalledTimes(1);
    const body = apiPostJson.mock.calls[0][1];
    expect(body.resume_doc_id).toBe("doc-1");
    expect(body.supporting_doc_ids).toHaveLength(2);
    expect(body.extra_text).toContain("Git");
    expect(body.extra_text).toContain("I know Docker.");
  });

  it("allows a retry after a failure", async () => {
    const p = payload();
    setPendingAnalysis(p);
    apiPostJson.mockRejectedValueOnce(new Error("boom"));
    await expect(startPendingAnalysis(p)).rejects.toThrow("boom");
    expect(await startPendingAnalysis(p)).toBe("analysis-1");
    expect(apiPostJson).toHaveBeenCalledTimes(2);
  });
});
