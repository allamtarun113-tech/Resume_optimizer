import { describe, expect, it } from "vitest";
import { safeNextPath } from "./redirect";

describe("safeNextPath", () => {
  it("keeps relative paths", () => {
    expect(safeNextPath("/analysis/123")).toBe("/analysis/123");
  });

  it.each([
    "https://evil.com",
    "//evil.com",
    "/\\evil.com",
    "",
    undefined,
    ["/a"],
  ])("rejects %s", (value) => {
    expect(safeNextPath(value)).toBe("/");
  });
});
