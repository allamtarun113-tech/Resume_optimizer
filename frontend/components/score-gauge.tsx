import { scoreTone } from "@/lib/results";

const RADIUS = 52;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const TONE_CLASS = {
  good: "text-emerald-600 dark:text-emerald-400",
  ok: "text-amber-500 dark:text-amber-400",
  low: "text-rose-600 dark:text-rose-400",
};

export function ScoreGauge({ score, label }: { score: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        viewBox="0 0 120 120"
        className="size-32 sm:size-36"
        role="img"
        aria-label={`${label}: ${clamped}%`}
      >
        <circle
          cx="60"
          cy="60"
          r={RADIUS}
          fill="none"
          strokeWidth="9"
          className="stroke-muted"
        />
        <circle
          cx="60"
          cy="60"
          r={RADIUS}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          stroke="currentColor"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - clamped / 100)}
          transform="rotate(-90 60 60)"
          className={TONE_CLASS[scoreTone(clamped)]}
        />
        <text
          x="60"
          y="60"
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-foreground text-[28px] font-bold tabular-nums"
        >
          {clamped}%
        </text>
      </svg>
      <span className="max-w-36 text-center text-sm text-muted-foreground">
        {label}
      </span>
    </div>
  );
}
