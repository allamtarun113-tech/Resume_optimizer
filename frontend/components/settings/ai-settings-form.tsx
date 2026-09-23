"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2Icon,
  ExternalLinkIcon,
  KeyRoundIcon,
  Loader2Icon,
  ShieldCheckIcon,
  Trash2Icon,
  WalletIcon,
} from "lucide-react";
import { toast } from "sonner";
import { apiDelete, apiFetch, apiPostJson } from "@/lib/api";
import type { AiSettings, AiSettingsUpdate, ModelList } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const SAME = "__same__";
const KEYS_URL = "https://platform.openai.com/api-keys";

export function AiSettingsForm() {
  const [saved, setSaved] = useState<AiSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [small, setSmall] = useState<string | null>(null);
  const [large, setLarge] = useState<string>(SAME);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load the saved settings; if a key is saved, fill the model list from it.
  useEffect(() => {
    apiFetch<AiSettings>("/settings/ai")
      .then(async (data) => {
        setSaved(data);
        if (!data.has_key) return;
        setSmall(data.model_small);
        setLarge(data.model_large ?? SAME);
        const list = await apiPostJson<ModelList>("/settings/ai/models", {});
        setModels(list.models);
      })
      .catch((e) => toast.error((e as Error).message));
  }, []);

  async function checkKey() {
    if (apiKey.trim().length < 20)
      return toast.error(
        "Paste your full OpenAI API key (it starts with sk-).",
      );
    setChecking(true);
    try {
      const list = await apiPostJson<ModelList>("/settings/ai/models", {
        api_key: apiKey.trim(),
      });
      setModels(list.models);
      setSmall((current) =>
        current && list.models.includes(current) ? current : list.default,
      );
      toast.success(
        `Key works. ${list.models.length} models available — pick one below.`,
      );
    } catch (e) {
      setModels([]);
      toast.error((e as Error).message);
    } finally {
      setChecking(false);
    }
  }

  async function save() {
    if (!small) return toast.error("Choose a model first.");
    setSaving(true);
    try {
      const body: AiSettingsUpdate = {
        api_key: apiKey.trim() || null,
        model_small: small,
        model_large: large === SAME ? null : large,
      };
      const response = await fetchPut(body);
      setSaved(response);
      setApiKey("");
      toast.success("Saved. You're ready to run analyses.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (
      !window.confirm(
        "Remove your OpenAI key? Analyses will stop until you add one again.",
      )
    )
      return;
    try {
      await apiDelete("/settings/ai");
      setSaved({
        has_key: false,
        key_last4: null,
        model_small: null,
        model_large: null,
        updated_at: null,
      });
      setModels([]);
      setSmall(null);
      setLarge(SAME);
      toast.success("Key removed.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const items = models.map((m) => ({ value: m, label: m }));
  const largeItems = [{ value: SAME, label: "Same as main model" }, ...items];

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <CardTitle className="flex items-center gap-2">
                <KeyRoundIcon className="size-5 text-primary" />
                OpenAI API key
              </CardTitle>
              <CardDescription>
                Used only for your own analyses and interview prep.
              </CardDescription>
            </div>
            {saved === null ? (
              <Skeleton className="h-6 w-28" />
            ) : saved.has_key ? (
              <Badge className="gap-1 bg-emerald-600 text-white dark:bg-emerald-500">
                <CheckCircle2Icon />
                Connected
              </Badge>
            ) : (
              <Badge variant="outline">Not connected</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {saved?.has_key && (
            <div className="rounded-lg border bg-muted/40 px-4 py-3 text-sm">
              Saved key ending in{" "}
              <span className="font-mono font-medium">
                •••• {saved.key_last4}
              </span>
              {saved.model_small && (
                <>
                  {" "}
                  · model{" "}
                  <span className="font-medium">{saved.model_small}</span>
                </>
              )}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="api-key">
              {saved?.has_key ? "Replace key (optional)" : "API key"}
            </Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id="api-key"
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder="sk-proj-…"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="font-mono"
              />
              <Button
                variant="outline"
                onClick={checkKey}
                disabled={checking || !apiKey.trim()}
              >
                {checking && <Loader2Icon className="animate-spin" />}
                Check key
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Paste a key, click Check key, then choose a model.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label>Main model</Label>
              <Select
                items={items}
                value={small}
                onValueChange={(v) => setSmall(v as string | null)}
                disabled={models.length === 0}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Check your key first" />
                </SelectTrigger>
                <SelectContent>
                  {items.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                      {item.value === "gpt-4o-mini" && (
                        <span className="text-xs text-muted-foreground">
                          recommended
                        </span>
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Used for reading documents, matching and learning paths.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Advanced model (optional)</Label>
              <Select
                items={largeItems}
                value={large}
                onValueChange={(v) => setLarge((v as string | null) ?? SAME)}
                disabled={models.length === 0}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {largeItems.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Used for resume suggestions and interview questions.
              </p>
            </div>
          </div>
        </CardContent>
        <CardFooter className="flex flex-wrap justify-between gap-3">
          <Button onClick={save} disabled={saving || !small}>
            {saving && <Loader2Icon className="animate-spin" />}
            Save settings
          </Button>
          {saved?.has_key && (
            <Button
              variant="ghost"
              onClick={remove}
              className="text-destructive"
            >
              <Trash2Icon />
              Remove key
            </Button>
          )}
        </CardFooter>
      </Card>

      <div className="flex flex-col gap-4">
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ExternalLinkIcon className="size-4 text-primary" />
              Get a key
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex list-decimal flex-col gap-1.5 pl-4 text-sm text-muted-foreground">
              <li>
                Open{" "}
                <a
                  href={KEYS_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary underline-offset-4 hover:underline"
                >
                  platform.openai.com/api-keys
                </a>
              </li>
              <li>Click “Create new secret key” and copy it.</li>
              <li>Make sure your account has a little credit (Billing).</li>
            </ol>
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheckIcon className="size-4 text-primary" />
              Private by design
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Your key is encrypted before it’s stored and is never shown again,
            only its last 4 characters. Remove it any time.
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <WalletIcon className="size-4 text-primary" />
              What it costs
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            About $0.002 per analysis with gpt-4o-mini, including interview
            prep. Repeat runs of the same inputs are free (cached).
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function fetchPut(body: AiSettingsUpdate): Promise<AiSettings> {
  return apiFetch<AiSettings>("/settings/ai", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
