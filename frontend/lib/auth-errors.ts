// Supabase auth error codes -> messages. Never echo raw query or hash text to the page.

const MESSAGES: Record<string, string> = {
  otp_expired:
    "That link was already used or has expired. If you just confirmed your email, sign in below.",
  flow_state_not_found:
    "That link was already used or has expired. If you just confirmed your email, sign in below.",
  bad_code_verifier:
    "Open the confirmation link in the same browser you signed up with, or sign in below.",
  email_not_confirmed:
    "Confirm your email first: check your inbox for the confirmation link.",
};

export const DEFAULT_AUTH_ERROR = "Sign-in failed. Please try again.";

export function authErrorMessage(code: string | null | undefined): string {
  return (code && MESSAGES[code]) || DEFAULT_AUTH_ERROR;
}

// Supabase reports some errors in the URL fragment (#error_code=...), which only the
// browser sees. Returns the error code, if any.
export function hashErrorCode(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  return params.get("error_code") ?? params.get("error");
}
