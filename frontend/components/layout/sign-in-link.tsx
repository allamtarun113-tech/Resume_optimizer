"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";

// Header "Sign in" button, hidden on the sign-in page itself.
export function SignInLink() {
  const pathname = usePathname();
  if (pathname.startsWith("/login")) return null;
  return (
    <Button nativeButton={false} render={<Link href="/login" />}>
      Sign in
    </Button>
  );
}
