import { Link } from "@tanstack/react-router";
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

/** PTF-07: the semaphore of a portfolio's policy; `warning` in amber and `broken` in red,
 * with the reason of the latest review's verdict and a link to the policy. */
export function PolicySemaphore({
  policyId,
  semaphore,
  reason,
}: {
  policyId: number;
  semaphore: string | null | undefined;
  reason: string | null | undefined;
}) {
  const { t } = useTranslation();
  if (!semaphore) return null;
  const alarming = semaphore === "warning" || semaphore === "broken";
  return (
    <div
      className={
        semaphore === "broken"
          ? "grid gap-1 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
          : alarming
            ? "grid gap-1 rounded-md border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
            : "flex flex-wrap items-center gap-2 text-sm"
      }
    >
      <span className="flex flex-wrap items-center gap-2">
        <span>{t("reviews.semaphore.thesis")}</span>
        <SemaphoreBadge semaphore={semaphore} />
      </span>
      {alarming && reason && <span>{reason}</span>}
      {alarming && (
        <Link
          to="/policies/$policyId"
          params={{ policyId: String(policyId) }}
          className="justify-self-start underline"
        >
          {t("reviews.semaphore.toPolicy")}
        </Link>
      )}
    </div>
  );
}
