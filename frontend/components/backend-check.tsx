"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";

// Phase 0 exit check: authenticated round-trip to the FastAPI backend.
export function BackendCheck() {
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function check() {
    setLoading(true);
    try {
      const me = await apiFetch<MeResponse>("/health/me");
      setResult(`Backend verified you as ${me.email ?? me.user_id}`);
    } catch (e) {
      setResult(`Backend check failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-2">
      <Button variant="outline" onClick={check} disabled={loading}>
        {loading ? "Checking…" : "Check backend connection"}
      </Button>
      {result && <p className="text-sm text-muted-foreground">{result}</p>}
    </div>
  );
}
