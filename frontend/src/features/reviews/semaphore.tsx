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

const BOX: Record<Semaphore, string> = {
  good: "border-green-300 bg-green-50 text-green-900 dark:border-green-900 dark:bg-green-950 dark:text-green-200",
  warning:
    "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200",
  broken:
    "border-red-300 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200",
};

/** PTF-07, THS-04: the semaphore of a policy's active version in a box of its colour, with
 * the badge and the verdict text of the latest review (`reason`). On `card`s (dashboard,
 * portfolio list) only `warning` and `broken` get a box, without the verdict text and with
 * a link to the policy; on a `page` the box is always there. It says nothing about what to
 * do: that is for the rebalance page (RB-25). */
export function PolicySemaphore({
  policyId,
  semaphore,
  reason,
  variant = "page",
  showLink = true,
}: {
  policyId: number;
  semaphore: string | null | undefined;
  reason?: string | null;
  variant?: "page" | "card";
  showLink?: boolean;
}) {
  const { t } = useTranslation();
  if (!semaphore || !isSemaphore(semaphore)) return null;
  const card = variant === "card";
  const boxed = !card || semaphore !== "good";
  return (
    <div
      className={
        boxed
          ? `grid gap-1 rounded-md border p-2 text-sm ${BOX[semaphore]}`
          : "flex flex-wrap items-center gap-2 text-sm"
      }
    >
      <span className="flex flex-wrap items-center gap-2">
        <span>{t("reviews.semaphore.thesis")}</span>
        <SemaphoreBadge semaphore={semaphore} />
      </span>
      {!card && reason && <span>{reason}</span>}
      {showLink && boxed && (
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
