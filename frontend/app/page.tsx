import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { Button } from "@/components/ui/button";

export default async function Home() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const email = data?.claims?.email as string | undefined;

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-4 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">
        Resume Optimizer
      </h1>
      <p className="max-w-md text-muted-foreground">
        Find out how well you fit a job, what to add to your resume, what to
        learn next, and what interviewers will ask.
      </p>
      {data?.claims ? (
        <div className="flex flex-col items-center gap-4">
          <p className="text-sm text-muted-foreground">Signed in as {email}</p>
          <div className="flex flex-wrap justify-center gap-3">
            <Button nativeButton={false} render={<Link href="/analyze" />}>
              New analysis
            </Button>
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/history" />}
            >
              Your analyses
            </Button>
          </div>
        </div>
      ) : (
        <Button nativeButton={false} render={<Link href="/login" />}>
          Get started
        </Button>
      )}
    </main>
  );
}
