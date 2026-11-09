import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatAmount, formatDateTime, formatUnits } from "@/lib/format";

import { useRebalance } from "./api";
import { actionLabel } from "./rebalance";

/** RB-16, RB-18, TL-02: a confirmed rebalance with its calculated instructions. */
export function RebalanceDetailPage({ rebalanceId }: { rebalanceId: number }) {
  const { t } = useTranslation();
  const rebalance = useRebalance(rebalanceId);
  if (rebalance.error) return <FormError error={rebalance.error} />;
  if (!rebalance.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const r = rebalance.data;
  const precise = r.precise_amounts;
  return (
    <div className="grid gap-4">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold">
          {t("rebalance.detail.title", { date: formatDateTime(r.confirmed_at) })}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("rebalance.detail.facts", {
            contribution: formatAmount(r.contribution, precise),
            withdrawal: formatAmount(r.withdrawal, precise),
          })}
          <Link
            to="/snapshots/$snapshotId"
            params={{ snapshotId: String(r.input_snapshot_id) }}
            className="underline"
          >
            {t("rebalance.detail.valuesBefore")}
          </Link>
          {r.result_snapshot_id !== null && (
            <>
              {" · "}
              <Link
                to="/snapshots/$snapshotId"
                params={{ snapshotId: String(r.result_snapshot_id) }}
                className="underline"
              >
                {t("rebalance.detail.valuesAfter")}
              </Link>
            </>
          )}{" "}
          ·{" "}
          <Link
            to="/portfolios/$portfolioId"
            params={{ portfolioId: String(r.portfolio_id) }}
            className="underline"
          >
            {t("rebalance.detail.portfolio")}
          </Link>{" "}
          ·{" "}
          <Link
            to="/rebalances/$rebalanceId/report"
            params={{ rebalanceId: String(r.id) }}
            className="underline"
          >
            {t("rebalance.detail.report")}
          </Link>
        </p>
        {r.mode === "sell_all" && (
          <p className="text-sm font-medium text-destructive">{t("rebalance.detail.sellAll")}</p>
        )}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("rebalance.detail.phase")}</TableHead>
            <TableHead>{t("rebalance.detail.position")}</TableHead>
            <TableHead>{t("rebalance.detail.action")}</TableHead>
            <TableHead>{t("rebalance.detail.broker")}</TableHead>
            <TableHead className="text-right">{t("rebalance.detail.calculatedUnits")}</TableHead>
            <TableHead className="text-right">{t("rebalance.detail.calculated")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {r.actions.map((a) => (
            <TableRow key={`${a.phase}${a.ticker}`}>
              <TableCell>{a.phase}</TableCell>
              <TableCell className="font-medium">{a.ticker}</TableCell>
              <TableCell>{actionLabel(a.action)}</TableCell>
              <TableCell>{a.broker ?? "–"}</TableCell>
              <TableCell className="text-right tabular-nums">
                {a.calculated_units === null ? "–" : formatUnits(a.calculated_units)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatAmount(a.calculated_amount, precise)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
