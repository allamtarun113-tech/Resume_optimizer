import { HistoryList } from "@/components/history-list";

export default function HistoryPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-4 py-10">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Your analyses</h1>
        <p className="text-muted-foreground">
          Every job you checked, newest first. Open one to see its results, or
          try the same resume against another job.
        </p>
      </div>
      <HistoryList />
    </main>
  );
}
