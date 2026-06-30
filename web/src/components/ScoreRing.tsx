import { scoreTier } from "@/lib/format";

// Prominenter, kreisförmiger Score-Indikator (0–100).
export default function ScoreRing({
  score,
  size = 72,
}: {
  score: number;
  size?: number;
}) {
  const tier = scoreTier(score);
  const stroke = 6;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const dash = circ * pct;

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      title={`Performance-Potential-Score: ${score} (keine Garantie)`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#27272a"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tier.ring}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ - dash}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-lg font-bold leading-none ${tier.text}`}>
          {Math.round(score)}
        </span>
        <span className="text-[9px] uppercase tracking-wide text-neutral-500">
          Score
        </span>
      </div>
    </div>
  );
}
