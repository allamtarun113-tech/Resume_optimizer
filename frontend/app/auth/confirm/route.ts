import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeNextPath } from "@/lib/redirect";

const OTP_TYPES: EmailOtpType[] = [
  "signup",
  "email",
  "invite",
  "magiclink",
  "recovery",
  "email_change",
];

// Email links (confirm sign-up, etc.) point here with a token hash, set up in the
// Supabase email templates. Unlike the PKCE code flow in /auth/callback, verifying a
// token hash works when the link is opened on a different device or browser.
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = safeNextPath(searchParams.get("next"));

  let errorCode = "auth";
  if (tokenHash && type && OTP_TYPES.includes(type)) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({
      type,
      token_hash: tokenHash,
    });
    if (!error) return NextResponse.redirect(`${origin}${next}`);
    errorCode = error.code ?? "auth";
  }

  const url = new URL("/login", origin);
  url.searchParams.set("error", errorCode);
  return NextResponse.redirect(url);
}
