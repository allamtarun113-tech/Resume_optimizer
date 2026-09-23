import { createClient } from "@/lib/supabase/server";
import { Brand } from "@/components/layout/brand";
import { NavLinks } from "@/components/layout/nav-links";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import { SignInLink } from "@/components/layout/sign-in-link";

export async function SiteHeader() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const email = data?.claims?.email as string | undefined;

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-md print:hidden">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4">
        <Brand />
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          {email ? (
            <>
              <NavLinks />
              <ThemeToggle />
              <UserMenu email={email} />
            </>
          ) : (
            <>
              <ThemeToggle />
              <SignInLink />
            </>
          )}
        </div>
      </div>
    </header>
  );
}
