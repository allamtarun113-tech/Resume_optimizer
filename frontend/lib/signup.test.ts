import { describe, expect, it } from "vitest";
import { signUpOutcome } from "./signup";

describe("signUpOutcome", () => {
  it("signs in when a session is returned", () => {
    expect(signUpOutcome({ session: {}, user: { identities: [{}] } })).toBe(
      "signed_in",
    );
  });

  it("detects an existing confirmed account (empty identities)", () => {
    expect(signUpOutcome({ session: null, user: { identities: [] } })).toBe(
      "already_exists",
    );
  });

  it("otherwise a confirmation email was sent", () => {
    expect(signUpOutcome({ session: null, user: { identities: [{}] } })).toBe(
      "check_email",
    );
    expect(signUpOutcome({ session: null, user: null })).toBe("check_email");
    expect(signUpOutcome({ session: null, user: {} })).toBe("check_email");
  });
});
