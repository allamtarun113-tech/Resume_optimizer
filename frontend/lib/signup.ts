// Interprets supabase.auth.signUp() results when "Confirm email" is on.
//
// - A session means confirmation is off: the user is signed in right away.
// - For an email that already has a confirmed account, Supabase returns a user with an
//   empty `identities` list and sends no email.
// - Otherwise a confirmation email was sent (also re-sent for unconfirmed accounts).

export type SignUpOutcome = "signed_in" | "check_email" | "already_exists";

type SignUpData = {
  session: unknown | null;
  user: { identities?: unknown[] | null } | null;
};

export function signUpOutcome(data: SignUpData): SignUpOutcome {
  if (data.session) return "signed_in";
  if (
    data.user &&
    Array.isArray(data.user.identities) &&
    data.user.identities.length === 0
  )
    return "already_exists";
  return "check_email";
}
