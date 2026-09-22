import { LoginForm } from "@/components/login-form";
import { safeNextPath } from "@/lib/redirect";

// Map Supabase error codes to messages; never echo raw query text.
const ERROR_MESSAGES: Record<string, string> = {
  otp_expired:
    "That confirmation link is invalid or was already used. Try signing in — your account may already be confirmed.",
  flow_state_not_found:
    "Open the confirmation link in the same browser you signed up with.",
  bad_code_verifier:
    "Open the confirmation link in the same browser you signed up with.",
};

export default async function LoginPage(props: PageProps<"/login">) {
  const { next, error } = await props.searchParams;
  const nextPath = safeNextPath(next);

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-4">
      {error && (
        <p className="max-w-sm text-center text-sm text-destructive">
          {(typeof error === "string" && ERROR_MESSAGES[error]) ||
            "Sign-in failed. Please try again."}
        </p>
      )}
      <LoginForm next={nextPath} />
    </main>
  );
}
