import { describe, expect, it } from "vitest";
import { inboxLink, signUpOutcome } from "./signup";

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

describe("inboxLink", () => {
  it("links common webmail providers", () => {
    expect(inboxLink("a@gmail.com")?.name).toBe("Gmail");
    expect(inboxLink("a@GoogleMail.com")?.name).toBe("Gmail");
    expect(inboxLink("a@hotmail.co.uk")?.name).toBe("Outlook");
    expect(inboxLink("a@yahoo.in")?.name).toBe("Yahoo Mail");
    expect(inboxLink("a@icloud.com")?.url).toBe("https://www.icloud.com/mail");
  });

  it("returns null for other domains", () => {
    expect(inboxLink("student@university.edu")).toBeNull();
    expect(inboxLink("not-an-email")).toBeNull();
  });
});
