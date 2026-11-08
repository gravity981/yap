import i18n from "i18next";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";

export const SEMAPHORES = ["good", "warning", "broken"] as const;
type Semaphore = (typeof SEMAPHORES)[number];

/** REV-06: verdicts of reviews before scoring version 3, as semaphores. */
const LEGACY_VERDICTS: Record<string, Semaphore> = {
  intact: "good",
  needs_adaptation: "warning",
  broken: "broken",
};

/** The semaphore a verdict of any scoring version stands for (REV-03, REV-06). */
export function toSemaphore(verdict: string | null | undefined): string | null {
  if (!verdict) return null;
  return LEGACY_VERDICTS[verdict] ?? verdict;
}

function isSemaphore(value: string): value is Semaphore {
  return (SEMAPHORES as readonly string[]).includes(value);
}

/** The semaphore in the current language; null is "not reviewed" (THS-04). */
export function semaphoreLabel(semaphore: string | null | undefined): string {
  if (!semaphore) return i18n.t("domain.semaphore.none");
  return isSemaphore(semaphore) ? i18n.t(`domain.semaphore.${semaphore}`) : semaphore;
}

const DOT: Record<Semaphore, string> = {
  good: "bg-green-600",
  warning: "bg-amber-500",
  broken: "bg-red-600",
};

/** THS-04: the semaphore of a thesis (good, warning, broken), or "not reviewed". */
export function SemaphoreBadge({ semaphore }: { semaphore: string | null | undefined }) {
  useTranslation(); // re-render on a language change
  const label = semaphoreLabel(semaphore);
  if (!semaphore || !isSemaphore(semaphore)) {
    return <Badge variant="outline">{label}</Badge>;
  }
  const variant =
    semaphore === "broken" ? "destructive" : semaphore === "warning" ? "warning" : "success";
  return (
    <Badge variant={variant} className="gap-1.5">
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT[semaphore]}`} />
      {label}
    </Badge>
  );
}
