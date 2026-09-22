// Only allow same-site relative paths, to prevent open redirects.
export function safeNextPath(next: unknown, fallback = "/"): string {
  return typeof next === "string" &&
    next.startsWith("/") &&
    !next.startsWith("//") &&
    !next.startsWith("/\\")
    ? next
    : fallback;
}
