import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { SignOutButton } from "@/components/sign-out-button";

export async function SiteHeader() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims);

  return (
    <header className="border-b print:hidden">
      <nav className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <Link href="/" className="font-semibold tracking-tight">
          Resume Optimizer
        </Link>
        {signedIn && (
          <div className="ml-auto flex items-center gap-1 text-sm sm:gap-3">
            <Link
              href="/analyze"
              className="rounded-md px-2 py-1 hover:bg-muted"
            >
              New analysis
            </Link>
            <Link
              href="/history"
              className="rounded-md px-2 py-1 hover:bg-muted"
            >
              History
            </Link>
            <SignOutButton />
          </div>
        )}
      </nav>
    </header>
  );
}
