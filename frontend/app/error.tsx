"use client"; // Error boundaries must be Client Components

import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Error({ retry }: { error: Error; retry: () => void }) {
  return (
    <main className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-4 p-4 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">
        Something went wrong
      </h1>
      <p className="text-muted-foreground">
        This page hit an unexpected error. Your analyses are safe; try again, or
        go back to the start.
      </p>
      <div className="flex gap-3">
        <Button onClick={() => retry()}>Try again</Button>
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href="/" />}
        >
          Home
        </Button>
      </div>
    </main>
  );
}
