import i18n from "i18next";

import { statusLabel } from "@/features/theses/status";
import { currentLocale } from "@/i18n";
import { formatAmount } from "@/lib/format";

import type { TimelineEvent } from "./api";

type Params = Record<string, unknown>;

const text = (value: unknown) => String(value ?? "");

/** A review result, e.g. "needs adaptation, 7 / 10, modified" (TL-02). */
function reviewResult(p: Params): string {
  const parts: string[] = [];
  if (p.verdict) parts.push(statusLabel(text(p.verdict)));
  if (typeof p.total === "number") {
    const total = new Intl.NumberFormat(currentLocale(), { maximumFractionDigits: 1 });
    parts.push(i18n.t("timeline.summary.score", { total: total.format(p.total) }));
  }
  if (p.modified) parts.push(i18n.t("timeline.summary.modified"));
  return parts.join(", ");
}

/** NFR-10: the summary of an event in the UI language, written from the values stored with
 * it; events from before the values were stored keep their English summary. */
export function eventSummary(event: TimelineEvent): string {
  const p = event.params as Params | null | undefined;
  if (!p) return event.summary;
  switch (event.type) {
    case "policy_activated": {
      const names = Array.isArray(p.portfolios) ? p.portfolios.map(text) : [];
      const values = {
        version: text(p.version),
        portfolios: names.length ? names.join(", ") : i18n.t("timeline.summary.noPortfolios"),
        note: text(p.note),
      };
      return p.note
        ? i18n.t("timeline.summary.policyActivatedNote", values)
        : i18n.t("timeline.summary.policyActivated", values);
    }
    case "portfolio_assigned": {
      const values = {
        portfolio: text(p.portfolio),
        policy: text(p.policy),
        version: text(p.version),
      };
      return p.created
        ? i18n.t("timeline.summary.portfolioCreated", values)
        : i18n.t("timeline.summary.portfolioReassigned", values);
    }
    case "rebalance_confirmed": {
      const amount = (value: unknown) => formatAmount(text(value), Boolean(p.precise));
      const values = {
        portfolio: text(p.portfolio),
        sold: amount(p.sold),
        bought: amount(p.bought),
        withdrawal: amount(p.withdrawal),
      };
      return p.withdrawal
        ? i18n.t("timeline.summary.rebalanceWithdrawal", values)
        : i18n.t("timeline.summary.rebalance", values);
    }
    case "thesis_review_confirmed":
      return i18n.t("timeline.summary.thesisReview", {
        title: text(p.title),
        revision: text(p.revision),
        result: reviewResult(p),
      });
    case "policy_review_confirmed":
      return i18n.t("timeline.summary.policyReview", {
        version: text(p.version),
        result: reviewResult(p),
      });
    case "thesis_revised":
      return i18n.t("timeline.summary.thesisRevised", {
        title: text(p.title),
        revision: text(p.revision),
        version: text(p.version),
        used: text(p.used_revision),
      });
    default:
      return event.summary;
  }
}
