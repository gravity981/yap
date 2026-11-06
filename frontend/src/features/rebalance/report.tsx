import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, unwrap } from "@/api/client";
import { AllocationBars, TypePie } from "@/components/charts";
import { FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePortfolio } from "@/features/portfolios/api";
import { formatAmount, formatDateTime } from "@/lib/format";

import { usePlan, useRebalance, type Result } from "./api";
import { CalculationSteps } from "./explanation";
import { actionLabel, CashCard, InstructionCards, PlanView, ResultTable } from "./rebalance";

/** RB-19: a print-optimised report; "Save as PDF" in the browser's print dialog. */
function ReportLayout({
  title,
  facts,
  children,
}: {
  title: string;
  facts: string[];
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <article className="mx-auto grid max-w-5xl gap-6 print:max-w-none">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {facts.map((f) => (
            <p key={f} className="text-sm text-muted-foreground">
              {f}
            </p>
          ))}
        </div>
        <Button className="no-print" onClick={() => window.print()}>
          {t("rebalance.report.print")}
        </Button>
      </header>
      {children}
    </article>
  );
}

/** Allocation after rebalancing: bars per position against target, pie by type. */
function ResultCharts({ result }: { result: Result }) {
  const byType = new Map<string, number>();
  for (const p of result.positions)
    byType.set(p.type, (byType.get(p.type) ?? 0) + Number(p.value_after));
  return (
    <section className="grid gap-6 break-inside-avoid lg:grid-cols-[2fr_1fr] print:grid-cols-[2fr_1fr]">
      <AllocationBars
        rows={result.positions.map((p) => ({
          ticker: p.ticker,
          name: p.name,
          allocation: Number(p.allocation_after_pct),
          target: p.target_pct === null ? null : Number(p.target_pct),
          buyAbs: null,
          sellAbs: null,
          status: p.in_policy ? "within_band" : "not_in_policy",
        }))}
      />
      <TypePie shares={[...byType].map(([type, value]) => ({ type, value }))} />
    </section>
  );
}

export function PlanReportPage({
  portfolioId,
  snapshotId,
  contribution,
  withdrawal,
}: {
  portfolioId: number;
  snapshotId?: number;
  contribution?: string;
  withdrawal?: string;
}) {
  const { t } = useTranslation();
  const portfolio = usePortfolio(portfolioId);
  const plan = usePlan(portfolioId, snapshotId, contribution, withdrawal);
  if (plan.error) return <FormError error={plan.error} />;
  if (!plan.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const p = plan.data;
  return (
    <ReportLayout
      title={t("rebalance.report.planTitle", { name: portfolio.data?.name ?? "" })}
      facts={[
        t("rebalance.report.planPolicy", {
          version: p.policy_version_label,
          date: formatDateTime(p.snapshot_taken_at),
        }),
        t("rebalance.report.planFacts", {
          contribution: formatAmount(p.contribution, p.precise_amounts),
          withdrawal: formatAmount(p.withdrawal, p.precise_amounts),
          date: formatDateTime(new Date().toISOString()),
        }),
      ]}
    >
      <PlanView plan={p} printable />
      <ResultCharts result={p.result} />
    </ReportLayout>
  );
}

export function ConfirmedReportPage({ rebalanceId }: { rebalanceId: number }) {
  const { t } = useTranslation();
  const rebalance = useRebalance(rebalanceId);
  const result = useQuery({
    queryKey: ["rebalances", rebalanceId, "result"],
    queryFn: () =>
      unwrap(
        api.GET("/api/rebalances/{rebalance_id}/result", {
          params: { path: { rebalance_id: rebalanceId } },
        }),
      ),
  });
  const portfolio = usePortfolio(rebalance.data?.portfolio_id ?? 0);
  const error = rebalance.error ?? result.error;
  if (error) return <FormError error={error} />;
  if (!rebalance.data || !result.data)
    return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const r = rebalance.data;
  const precise = r.precise_amounts;
  return (
    <ReportLayout
      title={t("rebalance.report.confirmedTitle", { name: portfolio.data?.name ?? "" })}
      facts={[
        t("rebalance.report.confirmedFacts", {
          date: formatDateTime(r.confirmed_at),
          contribution: formatAmount(r.contribution, precise),
          withdrawal: formatAmount(r.withdrawal, precise),
        }),
      ]}
    >
      <InstructionCards
        instructions={r.actions.map((a) => ({
          phase: a.phase,
          ticker: a.ticker,
          action: a.action,
          broker: a.broker,
          amount: a.executed_amount,
          units: a.executed_units,
          whole_units: a.whole_units,
        }))}
        precise={precise}
      />
      <Table aria-label={t("rebalance.report.table")}>
        <TableHeader>
          <TableRow>
            <TableHead>{t("rebalance.detail.position")}</TableHead>
            <TableHead>{t("rebalance.detail.action")}</TableHead>
            <TableHead className="text-right">{t("rebalance.detail.calculated")}</TableHead>
            <TableHead className="text-right">{t("rebalance.detail.executed")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {r.actions.map((a) => (
            <TableRow key={`${a.phase}${a.ticker}`}>
              <TableCell className="font-medium">{a.ticker}</TableCell>
              <TableCell>{actionLabel(a.action)}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatAmount(a.calculated_amount, precise)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatAmount(a.executed_amount, precise)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <CashCard
        contribution={r.contribution}
        withdrawal={r.withdrawal}
        result={result.data}
        precise={precise}
      />
      <CalculationSteps
        contribution={r.contribution}
        withdrawal={r.withdrawal}
        result={result.data}
        precise={precise}
        open
      />
      <ResultTable result={result.data} precise={precise} open />
      <ResultCharts result={result.data} />
    </ReportLayout>
  );
}
