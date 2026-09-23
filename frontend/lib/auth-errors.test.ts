import { describe, expect, it } from "vitest";
import {
  DEFAULT_AUTH_ERROR,
  authErrorMessage,
  hashErrorCode,
} from "./auth-errors";

describe("auth errors", () => {
  it("maps known codes and falls back for anything else", () => {
    expect(authErrorMessage("otp_expired")).toMatch(
      /already used or has expired/,
    );
    expect(authErrorMessage("auth")).toBe(DEFAULT_AUTH_ERROR);
    expect(authErrorMessage("<script>")).toBe(DEFAULT_AUTH_ERROR);
    expect(authErrorMessage(null)).toBe(DEFAULT_AUTH_ERROR);
  });

  it("reads the error code from the URL fragment", () => {
    const hash =
      "#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid";
    expect(hashErrorCode(hash)).toBe("otp_expired");
    expect(hashErrorCode("#error=access_denied")).toBe("access_denied");
    expect(hashErrorCode("")).toBeNull();
  });
});
