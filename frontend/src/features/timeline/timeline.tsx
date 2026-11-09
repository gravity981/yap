import { Link } from "@tanstack/react-router";
import i18n from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { useCompare, usePolicies } from "@/features/policies/api";
import { VersionDiffView } from "@/features/policies/positions";
import { usePortfolios } from "@/features/portfolios/api";
import { useRebalance } from "@/features/rebalance/api";
import { actionLabel } from "@/features/rebalance/rebalance";
import { ReviewDetails } from "@/features/reviews/review";
import { formatAmount, formatDateTime } from "@/lib/format";

import {
  EVENT_TYPES,
  useTimeline,
  useVersionById,
  type EventType,
  type TimelineEvent,
} from "./api";
import { eventSummary } from "./summary";

/** Local date (yyyy-mm-dd) to the UTC instant at the start of that local day (NFR-14). */
export function localDayStart(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y!, m! - 1, d!).toISOString();
}

export function localDayEnd(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y!, m! - 1, d! + 1).toISOString();
}

function typeLabel(type: string): string {
  return (EVENT_TYPES as readonly string[]).includes(type)
    ? i18n.t(`timeline.types.${type as EventType}`)
    : type;
}

/** TL-01, TL-03 */
export function TimelinePage() {
  const { t } = useTranslation();
  const portfolios = usePortfolios();
  const policies = usePolicies();
  const [portfolioId, setPortfolioId] = useState("");
  const [policyId, setPolicyId] = useState("");
  const [types, setTypes] = useState<EventType[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const events = useTimeline({
    portfolioId: portfolioId ? Number(portfolioId) : undefined,
    policyId: policyId ? Number(policyId) : undefined,
    types,
    start: from ? localDayStart(from) : undefined,
    end: to ? localDayEnd(to) : undefined,
  });

  return (
    <div className="grid gap-4">
      <PageTitle title={t("timeline.title")} description={t("timeline.description")} />
      <div className="flex flex-wrap items-end gap-3" aria-label={t("timeline.filter.label")}>
        <div className="grid gap-1.5">
          <Label htmlFor="filter-portfolio">{t("timeline.filter.portfolio")}</Label>
          <NativeSelect
            id="filter-portfolio"
            className="w-44"
            value={portfolioId}
            onChange={(e) => setPortfolioId(e.target.value)}
          >
            <option value="">{t("timeline.filter.all")}</option>
            {portfolios.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="filter-policy">{t("timeline.filter.policy")}</Label>
          <NativeSelect
            id="filter-policy"
            className="w-44"
            value={policyId}
            onChange={(e) => setPolicyId(e.target.value)}
          >
            <option value="">{t("timeline.filter.all")}</option>
            {policies.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="filter-from">{t("timeline.filter.from")}</Label>
          <Input
            id="filter-from"
            type="date"
            className="w-40"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="filter-to">{t("timeline.filter.to")}</Label>
          <Input
            id="filter-to"
            type="date"
            className="w-40"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <fieldset className="flex flex-wrap gap-3 pb-2 text-sm">
          <legend className="sr-only">{t("timeline.filter.types")}</legend>
          {EVENT_TYPES.map((type) => (
            <label key={type} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={types.includes(type)}
                onChange={(e) =>
                  setTypes(e.target.checked ? [...types, type] : types.filter((x) => x !== type))
                }
              />
              {t(`timeline.types.${type}`)}
            </label>
          ))}
        </fieldset>
      </div>
      <FormError error={events.error} />
      {events.data && <EventList events={[...events.data].reverse()} />}
    </div>
  );
}

/** Newest first; each entry opens its details (TL-02). */
export function EventList({
  events,
  compact = false,
}: {
  events: TimelineEvent[];
  compact?: boolean;
}) {
  const { t } = useTranslation();
  if (events.length === 0) return <p className="text-muted-foreground">{t("timeline.noEvents")}</p>;
  return (
    <ol className="grid gap-2">
      {events.map((e) => (
        <li key={e.id} className="rounded-md border">
          <details>
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 p-3 text-sm">
              <Badge variant="outline">{typeLabel(e.type)}</Badge>
              <span>{eventSummary(e)}</span>
              <span className="ml-auto text-muted-foreground">{formatDateTime(e.occurred_at)}</span>
            </summary>
            {!compact && (
              <div className="border-t p-3">
                <EventDetails event={e} />
              </div>
            )}
          </details>
        </li>
      ))}
    </ol>
  );
}

function EventDetails({ event }: { event: TimelineEvent }) {
  switch (event.type) {
    case "policy_activated":
      return <ActivationDetails versionId={event.policy_version_id} />;
    case "portfolio_assigned":
      return <AssignmentDetails event={event} />;
    case "rebalance_confirmed":
      return event.rebalance_id === null ? null : (
        <RebalanceDetails rebalanceId={event.rebalance_id} />
      );
    case "thesis_revised":
      return null; // events from before policies held their thesis: the summary says it all
    case "thesis_review_confirmed":
      return (
        <div className="grid gap-3">
          {event.policy_version_id !== null && <VersionLink versionId={event.policy_version_id} />}
          {event.review_id !== null && <ReviewDetails reviewId={event.review_id} />}
        </div>
      );
    case "policy_review_confirmed":
    case "review_confirmed":
    case "review_saved":
      return (
        <div className="grid gap-3">
          <VersionLink versionId={event.policy_version_id} />
          {event.review_id !== null && <ReviewDetails reviewId={event.review_id} />}
        </div>
      );
    default:
      return <p className="text-sm text-muted-foreground">{i18n.t("timeline.noDetails")}</p>;
  }
}

function ActivationDetails({ versionId }: { versionId: number | null }) {
  const { t } = useTranslation();
  const version = useVersionById(versionId);
  if (!version.data) return null;
  const v = version.data;
  return (
    <div className="grid gap-2 text-sm">
      <p>
        <Link
          to="/policies/$policyId"
          params={{ policyId: String(v.policy_id) }}
          className="underline"
        >
          {v.label}
        </Link>
        {v.change_note && `: ${v.change_note}`}
      </p>
      {v.version_no > 1 ? (
        <ActivationDiff policyId={v.policy_id} versionNo={v.version_no} />
      ) : (
        <p className="text-muted-foreground">{t("timeline.firstVersion")}</p>
      )}
    </div>
  );
}

function ActivationDiff({ policyId, versionNo }: { policyId: number; versionNo: number }) {
  const diff = useCompare(policyId, versionNo - 1, versionNo);
  return diff.data ? <VersionDiffView diff={diff.data} /> : null;
}

function AssignmentDetails({ event }: { event: TimelineEvent }) {
  const { t } = useTranslation();
  const version = useVersionById(event.policy_version_id);
  return (
    <p className="text-sm">
      {event.portfolio_id !== null && (
        <Link
          to="/portfolios/$portfolioId"
          params={{ portfolioId: String(event.portfolio_id) }}
          className="underline"
        >
          {t("timeline.portfolio")}
        </Link>
      )}
      {version.data && (
        <>
          {t("timeline.follows")}
          <Link
            to="/policies/$policyId"
            params={{ policyId: String(version.data.policy_id) }}
            className="underline"
          >
            {version.data.label}
          </Link>
        </>
      )}
    </p>
  );
}

function RebalanceDetails({ rebalanceId }: { rebalanceId: number }) {
  const { t } = useTranslation();
  const rebalance = useRebalance(rebalanceId);
  if (!rebalance.data) return null;
  const r = rebalance.data;
  return (
    <div className="grid gap-1 text-sm">
      <ul className="grid gap-0.5">
        {r.actions.map((a) => (
          <li key={`${a.phase}${a.ticker}`}>
            {a.ticker} {actionLabel(a.action)}:{" "}
            {formatAmount(a.calculated_amount, r.precise_amounts)}
          </li>
        ))}
      </ul>
      <Link
        to="/rebalances/$rebalanceId"
        params={{ rebalanceId: String(r.id) }}
        className="underline"
      >
        {t("timeline.openRebalance")}
      </Link>
    </div>
  );
}

function VersionLink({ versionId }: { versionId: number | null }) {
  const version = useVersionById(versionId);
  if (!version.data) return null;
  const v = version.data;
  return (
    <p className="text-sm">
      <Link
        to="/policies/$policyId"
        params={{ policyId: String(v.policy_id) }}
        className="underline"
      >
        {v.label}
      </Link>
      {v.change_note && `: ${v.change_note}`}
    </p>
  );
}
