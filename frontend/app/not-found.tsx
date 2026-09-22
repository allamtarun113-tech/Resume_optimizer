import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-4 p-4 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-muted-foreground">
        This page doesn&apos;t exist, or the analysis was deleted.
      </p>
      <Button nativeButton={false} render={<Link href="/history" />}>
        Your analyses
      </Button>
    </main>
  );
}
