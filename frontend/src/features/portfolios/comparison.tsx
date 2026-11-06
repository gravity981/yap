import i18n from "i18next";
import { AlertTriangle, CheckCircle2, CircleMinus, CircleSlash, TrendingDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AllocationBars, statusText, TypePie } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatAmount, formatDateTime, formatPct, formatPrice, formatUnits } from "@/lib/format";

import { AutoPriceInfo } from "@/features/prices/auto-price";

import type { Snapshot } from "./api";

/** Band status with icon and text, never colour alone. */
export function BandStatusBadge({ status }: { status: string }) {
  const text = statusText(status);
  switch (status) {
    case "above_sell_threshold":
      return (
        <Badge variant="warning">
          <AlertTriangle className="mr-1 size-3" aria-hidden />
          {text}
        </Badge>
      );
    case "below_buy_threshold":
      return (
        <Badge variant="warning">
          <TrendingDown className="mr-1 size-3" aria-hidden />
          {text}
        </Badge>
      );
    case "within_band":
      return (
        <Badge variant="success">
          <CheckCircle2 className="mr-1 size-3" aria-hidden />
          {text}
        </Badge>
      );
    case "not_in_policy":
      return (
        <Badge variant="secondary">
          <CircleSlash className="mr-1 size-3" aria-hidden />
          {text}
        </Badge>
      );
    default:
      return (
        <Badge variant="outline">
          <CircleMinus className="mr-1 size-3" aria-hidden />
          {text}
        </Badge>
      );
  }
}

const SOURCES = ["manual", "import", "rebalance"] as const;

/** Where a snapshot's values come from, in the current language. */
export function sourceLabel(source: string): string {
  return (SOURCES as readonly string[]).includes(source)
    ? i18n.t(`portfolios.source.${source as (typeof SOURCES)[number]}`)
    : source;
}

export function outsideBand(snapshot: Snapshot): number {
  return snapshot.rows.filter(
    (r) => r.status === "above_sell_threshold" || r.status === "below_buy_threshold",
  ).length;
}

/** CMP-02, CMP-05, CMP-07, CMP-10: a snapshot compared with its own policy version; units
 * and price are unknown for rows from before price tracking. */
export function ComparisonView({
  snapshot,
  precise = false,
}: {
  snapshot: Snapshot;
  precise?: boolean;
}) {
  const { t } = useTranslation();
  const byType = new Map<string, number>();
  for (const r of snapshot.rows) byType.set(r.type, (byType.get(r.type) ?? 0) + Number(r.value));

  return (
    <div className="grid gap-6">
      <p className="text-sm text-muted-foreground">
        {t("portfolios.comparison.taken", {
          date: formatDateTime(snapshot.taken_at),
          version: snapshot.policy_version_label,
          total: formatAmount(snapshot.total_value, precise),
        })}
        {snapshot.source !== "manual" &&
          t("portfolios.comparison.source", { source: sourceLabel(snapshot.source) })}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("portfolios.comparison.position")}</TableHead>
            <TableHead className="text-right">{t("portfolios.comparison.units")}</TableHead>
            <TableHead className="text-right">{t("portfolios.comparison.price")}</TableHead>
            <TableHead className="text-right">
              {t("portfolios.comparison.value", { currency: snapshot.currency })}
            </TableHead>
            <TableHead className="text-right">{t("portfolios.comparison.allocation")}</TableHead>
            <TableHead className="text-right">{t("portfolios.comparison.target")}</TableHead>
            <TableHead className="text-right">{t("portfolios.comparison.band")}</TableHead>
            <TableHead className="text-right">{t("portfolios.comparison.deviation")}</TableHead>
            <TableHead>{t("portfolios.comparison.status")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {snapshot.rows.map((r) => (
            <TableRow key={r.ticker}>
              <TableCell>
                <span className="font-medium">{r.ticker}</span>{" "}
                <span className="text-muted-foreground">{r.name}</span>{" "}
                {r.exit && <Badge variant="destructive">{t("portfolios.comparison.exit")}</Badge>}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {r.units === null || r.type === "cash_buffer" ? "–" : formatUnits(r.units)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {r.price === null || r.type === "cash_buffer" ? "–" : formatPrice(r.price)}
                {/* CMP-10: where an auto price came from, as of the snapshot (PRC-12) */}
                {r.auto && (
                  <span className="block">
                    <AutoPriceInfo
                      auto={r.auto}
                      currency={snapshot.currency}
                      reference={new Date(snapshot.taken_at)}
                    />
                  </span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatAmount(r.value, precise)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right tabular-nums">
                {formatPct(r.allocation_pct)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right tabular-nums">
                {r.target_pct === null ? "–" : formatPct(r.target_pct)}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right tabular-nums">
                {r.buy_abs_pct === null || r.sell_abs_pct === null
                  ? "–"
                  : `${formatPct(r.buy_abs_pct)} – ${formatPct(r.sell_abs_pct)}`}
              </TableCell>
              <TableCell className="whitespace-nowrap text-right tabular-nums">
                {r.deviation_pct === null
                  ? "–"
                  : `${Number(r.deviation_pct) > 0 ? "+" : ""}${formatPct(r.deviation_pct)}`}
              </TableCell>
              <TableCell>
                <BandStatusBadge status={r.status} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <AllocationBars
          rows={snapshot.rows.map((r) => ({
            ticker: r.ticker,
            name: r.name,
            allocation: Number(r.allocation_pct),
            target: r.target_pct === null ? null : Number(r.target_pct),
            buyAbs: r.buy_abs_pct === null ? null : Number(r.buy_abs_pct),
            sellAbs: r.sell_abs_pct === null ? null : Number(r.sell_abs_pct),
            status: r.status,
          }))}
        />
        <TypePie shares={[...byType].map(([type, value]) => ({ type, value }))} />
      </div>
    </div>
  );
}
