import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { isNoKeyError } from "./errors";

describe("isNoKeyError", () => {
  it("recognises the missing-key response", () => {
    expect(isNoKeyError(new ApiError(428, "Add your OpenAI API key"))).toBe(
      true,
    );
    expect(isNoKeyError(new ApiError(422, "bad"))).toBe(false);
    expect(isNoKeyError(new Error("x"))).toBe(false);
  });
});
