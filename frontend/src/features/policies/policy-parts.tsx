import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { Stars, formatScore } from "@/components/stars";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ReviewPane } from "@/features/reviews/pane";
import { formatDate } from "@/lib/format";

import { usePolicySharing, type Policy, type PolicySummary, type Version } from "./api";

const LEVELS = ["private", "text", "all"] as const;

/** POL-18: the sharing level as a badge. */
export function SharingBadge({ sharing }: { sharing: string }) {
  const { t } = useTranslation();
  const label = (LEVELS as readonly string[]).includes(sharing)
    ? t(`policies.sharing.badge.${sharing as (typeof LEVELS)[number]}`)
    : sharing;
  return <Badge variant="secondary">{label}</Badge>;
}

/** POL-19, REV-21: the score of the latest review as stars, the activation date, the date
 * of the latest review and the portfolios that follow the policy. */
export function PolicyFacts({ policy }: { policy: Policy | PolicySummary }) {
  const { t } = useTranslation();
  const latest = policy.latest_review;
  const facts = [
    policy.active_from && t("policies.facts.activeSince", { date: formatDate(policy.active_from) }),
    latest?.saved_at && t("policies.facts.lastReviewed", { date: formatDate(latest.saved_at) }),
    policy.portfolios.length > 0 &&
      t("policies.facts.usedBy", { portfolios: policy.portfolios.map((p) => p.name).join(", ") }),
  ].filter(Boolean);
  if (!policy.active_from) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      {latest?.total != null && (
        <>
          <Stars score={latest.total} label={t("reviews.score.totalLabel")} />
          <span className="font-semibold text-foreground tabular-nums">
            {formatScore(latest.total)}
          </span>
        </>
      )}
      {facts.length > 0 && <span>{facts.join(" · ")}</span>}
    </div>
  );
}

/** POL-20: reviews the active version again, without a new version. The result goes into
 * the review log and sets the score and the semaphore; its suggestions are taken over into
 * the draft, which is created if there is none (REV-07). */
export function ReviewAgain({ policy, versionLabel }: { policy: Policy; versionLabel: string }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Version | null>(null);
  return (
    <section className="grid gap-3 rounded-lg border p-4" aria-label={t("reviews.again.title")}>
      <h2 className="font-semibold">{t("reviews.again.title")}</h2>
      <p className="text-sm text-muted-foreground">
        {t("reviews.again.note", { version: versionLabel })}
      </p>
      {draft && (
        <Alert role="status">
          {t("reviews.again.takenOver", { version: draft.label })}{" "}
          <Link
            to="/policies/$policyId/draft"
            params={{ policyId: String(policy.id) }}
            className="underline"
          >
            {t("reviews.again.openDraft")}
          </Link>
        </Alert>
      )}
      <ReviewPane
        policyId={policy.id}
        target="active"
        brief={policy.pending_review ?? policy.latest_review}
        save={() => Promise.resolve()}
        onDraft={(d) => d && setDraft(d)}
      />
    </section>
  );
}

/** POL-18: private, the thesis, or thesis and target structure; only a reviewed active
 * version can be shared (REV-20). Shared policies are listed in the catalog (stage 3). */
export function Sharing({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  const sharing = usePolicySharing(policy.id);
  const reviewed = policy.latest_review !== null;
  return (
    <fieldset className="grid gap-2 rounded-lg border p-4">
      <legend className="px-1 font-semibold">{t("policies.sharing.title")}</legend>
      {LEVELS.map((level) => (
        <label
          key={level}
          className={
            policy.sharing === level
              ? "flex items-start gap-3 rounded-md border-2 border-primary p-3 text-sm"
              : "flex items-start gap-3 rounded-md border p-3 text-sm"
          }
        >
          <input
            type="radio"
            name={`sharing-${policy.id}`}
            className="mt-1"
            checked={policy.sharing === level}
            disabled={sharing.isPending || (level !== "private" && !reviewed)}
            onChange={() => sharing.mutate(level)}
          />
          <span>
            <span className="font-medium">{t(`policies.sharing.${level}.label`)}</span>
            <br />
            <span className="text-muted-foreground">{t(`policies.sharing.${level}.hint`)}</span>
          </span>
        </label>
      ))}
      {!reviewed && (
        <p className="text-sm text-muted-foreground">{t("policies.sharing.needsReview")}</p>
      )}
      <FormError error={sharing.error} />
    </fieldset>
  );
}
