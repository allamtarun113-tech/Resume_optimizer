import { AnalysisView } from "@/components/analysis-view";

export default async function AnalysisPage(props: PageProps<"/analysis/[id]">) {
  const { id } = await props.params;
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-10">
      <AnalysisView id={id} />
    </main>
  );
}
