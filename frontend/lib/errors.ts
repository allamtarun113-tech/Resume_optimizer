import { toast } from "sonner";
import { ApiError } from "@/lib/api";

// 428 = the user hasn't added an OpenAI key yet (or it can't be read).
export function isNoKeyError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 428;
}

type Navigate = (href: string) => void;

export function showApiError(error: unknown, navigate: Navigate): void {
  const message = (error as Error).message || "Something went wrong.";
  if (isNoKeyError(error)) {
    toast.error(message, {
      action: { label: "Open Settings", onClick: () => navigate("/settings") },
    });
    return;
  }
  toast.error(message);
}
