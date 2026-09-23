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

// A shortcut to the user's webmail inbox for common providers, else null.
const INBOXES: [RegExp, string, string][] = [
  [
    /^(gmail|googlemail)\.com$/,
    "Gmail",
    "https://mail.google.com/mail/u/0/#inbox",
  ],
  [
    /^(outlook|hotmail|live|msn)\.[a-z.]+$/,
    "Outlook",
    "https://outlook.live.com/mail/0/inbox",
  ],
  [/^(yahoo|ymail)\.[a-z.]+$/, "Yahoo Mail", "https://mail.yahoo.com/"],
  [/^(icloud|me|mac)\.com$/, "iCloud Mail", "https://www.icloud.com/mail"],
];

export function inboxLink(email: string): { name: string; url: string } | null {
  const domain = email.split("@").pop()?.trim().toLowerCase() ?? "";
  const match = INBOXES.find(([re]) => re.test(domain));
  return match ? { name: match[1], url: match[2] } : null;
}
