import Link from "next/link";
import { SparklesIcon } from "lucide-react";

export function BrandMark({ className = "size-8" }: { className?: string }) {
  return (
    <span
      className={`bg-brand-gradient inline-flex items-center justify-center rounded-lg text-white shadow-sm shadow-primary/30 ${className}`}
    >
      <SparklesIcon className="size-1/2" />
    </span>
  );
}

export function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <BrandMark />
      <span className="hidden font-semibold tracking-tight sm:inline">
        Resume Optimizer
      </span>
    </Link>
  );
}
