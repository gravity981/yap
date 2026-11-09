import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { Stars, formatScore } from "@/components/stars";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SemaphoreBadge } from "@/features/reviews/semaphore";
import { ReviewPane } from "@/features/reviews/pane";
import { formatDate } from "@/lib/format";

import { Input } from "@/components/ui/input";

import { usePolicySharing, useRenamePolicy, type Policy, type PolicySummary } from "./api";

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

/** POL-20, REV-26: the quick review of the active version, without a new version: the
 * verdict and the news. The result goes into the review log and gives the semaphore; the
 * score stays as it was. */
export function QuickReview({ policy, versionLabel }: { policy: Policy; versionLabel: string }) {
  const { t } = useTranslation();
  return (
    <section className="grid gap-3 rounded-lg border p-4" aria-label={t("reviews.again.title")}>
      <h2 className="font-semibold">{t("reviews.again.title")}</h2>
      <p className="text-sm text-muted-foreground">
        {t("reviews.again.note", { version: versionLabel })}
      </p>
      <ReviewPane
        policyId={policy.id}
        target="active"
        brief={policy.pending_review ?? policy.latest_review}
        save={() => Promise.resolve()}
        onDraft={() => undefined}
      />
    </section>
  );
}

/** POL-21: the name of the policy, with a button to rename it. */
export function PolicyName({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  const rename = useRenamePolicy(policy.id);
  const [name, setName] = useState<string | null>(null);
  if (name === null) {
    return (
      <>
        <h1 className="text-2xl font-semibold">{policy.name}</h1>
        {policy.archived_at === null && (
          <Button size="sm" variant="ghost" onClick={() => setName(policy.name)}>
            {t("policies.detail.rename")}
          </Button>
        )}
      </>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        rename.mutate(name, { onSuccess: () => setName(null) });
      }}
    >
      <Input
        aria-label={t("policies.detail.newName")}
        className="w-64"
        value={name}
        autoFocus
        onChange={(e) => setName(e.target.value)}
      />
      <Button type="submit" size="sm" disabled={rename.isPending}>
        {t("common.save")}
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => setName(null)}>
        {t("common.cancel")}
      </Button>
      <FormError error={rename.error} />
    </form>
  );
}

/** POL-22: while the draft has changes, the review box of the policy page is the draft's: the
 * review is made in the editor and belongs to the draft, not to the active version. */
export function DraftReview({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  const draft = policy.draft;
  if (!draft) return null;
  const review = draft.review;
  return (
    <section className="grid gap-3 rounded-lg border p-4" aria-label={t("reviews.draftBox.title")}>
      <h2 className="font-semibold">{t("reviews.draftBox.title")}</h2>
      <p className="text-sm text-muted-foreground">
        {t("reviews.draftBox.note", { version: draft.label })}
      </p>
      {review && review.total != null ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">{t("reviews.draftBox.reviewOf")}</span>
          <Stars score={review.total} label={t("reviews.score.totalLabel")} />
          <span className="font-semibold tabular-nums">{formatScore(review.total)}</span>
          <SemaphoreBadge semaphore={review.semaphore} />
          {review.outdated && (
            <Badge variant="warning">{t("reviews.result.noLongerMatches")}</Badge>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t("reviews.draftBox.none")}</p>
      )}
      <Button asChild variant="outline" className="w-fit">
        <Link to="/policies/$policyId/draft" params={{ policyId: String(policy.id) }}>
          {t("reviews.draftBox.openEditor")}
        </Link>
      </Button>
    </section>
  );
}

/** POL-18: private, the thesis, or thesis and target structure; only a reviewed active
 * version can be shared (REV-20). Shared policies are listed in the catalog (stage 3). */
export function Sharing({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  const sharing = usePolicySharing(policy.id);
  // Sharing needs a review with scores; a quick review has none (REV-20, REV-26)
  const reviewed = policy.latest_review?.total != null;
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
