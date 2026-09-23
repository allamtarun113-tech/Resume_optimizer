"use client";

import { useSyncExternalStore } from "react";
import { authErrorMessage, hashErrorCode } from "@/lib/auth-errors";

function subscribe(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

// Shows the sign-in error from ?error=… or, more precisely, from #error_code=….
export function AuthError({ queryCode }: { queryCode: string | null }) {
  const hashCode = useSyncExternalStore(
    subscribe,
    () => hashErrorCode(window.location.hash),
    () => null,
  );
  const code = hashCode ?? queryCode;
  if (!code) return null;
  return (
    <p className="max-w-sm text-center text-sm text-destructive">
      {authErrorMessage(code)}
    </p>
  );
}
