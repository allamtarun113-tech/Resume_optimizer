import { AuthError } from "@/components/auth-error";
import { LoginForm } from "@/components/login-form";
import { safeNextPath } from "@/lib/redirect";

export default async function LoginPage(props: PageProps<"/login">) {
  const { next, error } = await props.searchParams;
  const nextPath = safeNextPath(next);

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-4">
      <AuthError queryCode={typeof error === "string" ? error : null} />
      <LoginForm next={nextPath} />
    </main>
  );
}
