import { Star, StarHalf } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

const STARS = 10;

/** A score from 0 to 10 in steps of 0.5 as ten stars with half stars (REV-02). */
export function Stars({
  score,
  label,
  className,
}: {
  score: number;
  label?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const outOf = t("components.stars.outOf", { score: formatScore(score) });
  const text = label ? `${label}: ${outOf}` : outOf;
  return (
    <span
      role="img"
      aria-label={text}
      title={text}
      className={cn("inline-flex shrink-0 text-[var(--rating)]", className)}
    >
      {Array.from({ length: STARS }, (_, i) => {
        const filled = score - i;
        return (
          <span key={i} className="relative size-4" aria-hidden>
            <Star
              className={cn("absolute inset-0 size-4", filled < 1 && "text-muted-foreground/40")}
              fill={filled >= 1 ? "currentColor" : "none"}
              strokeWidth={1.5}
            />
            {filled === 0.5 && (
              <StarHalf className="absolute inset-0 size-4" fill="currentColor" strokeWidth={1.5} />
            )}
          </span>
        );
      })}
    </span>
  );
}

export function formatScore(score: number) {
  return score.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}
