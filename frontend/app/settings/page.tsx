import { AiSettingsForm } from "@/components/settings/ai-settings-form";

export default function SettingsPage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-10">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Resume Optimizer runs on your own OpenAI account. Add your API key and
          pick a model; you only pay OpenAI for what you use.
        </p>
      </div>
      <AiSettingsForm />
    </main>
  );
}
