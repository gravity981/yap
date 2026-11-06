import { Link, useNavigate } from "@tanstack/react-router";
import i18n from "i18next";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { NotAdvice } from "@/components/disclaimer";
import { FormError } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePortfolio } from "@/features/portfolios/api";
import { formatAmount, formatDateTime, formatPct, formatUnits } from "@/lib/format";

import { useConfirm, usePlan, useSimulation, type Plan, type Result } from "./api";
import { CalculationSteps } from "./explanation";

const PHASES = [
  { phase: "1A", title: "dips" },
  { phase: "1B", title: "sell" },
  { phase: "3", title: "buy" },
] as const;
// RB-22: phase 3 sells instead of buys when the withdrawal needs more than the cash
const WITHDRAWAL_SELL = "Sell (Withdrawal)";

// The actions as the API names them (domain/rebalancing.py), and their text keys
const ACTIONS = {
  Sell: "sell",
  "Sell All (Exit)": "sellAllExit",
  "Buy (Buffer)": "buyBuffer",
  Deploy: "deploy",
  "Sell & Deploy": "sellAndDeploy",
  Hold: "hold",
  "Buy (Below Target)": "buyBelowTarget",
  "Buy (At Target)": "buyAtTarget",
  "Sell (Withdrawal)": "sellWithdrawal",
} as const;

/** An action of the API in the current language; unknown ones (e.g. "-") as they are. */
export function actionLabel(action: string): string {
  const key = ACTIONS[action as keyof typeof ACTIONS];
  return key ? i18n.t(`rebalance.action.${key}`) : action;
}

function isToday(utc: string): boolean {
  return new Date(utc).toDateString() === new Date().toDateString();
}

/** RB-01 to RB-03, RB-11 to RB-16, RB-20, RB-22 */
export function RebalancePage({
  portfolioId,
  snapshotId,
}: {
  portfolioId: number;
  snapshotId?: number;
}) {
  const { t } = useTranslation();
  const portfolio = usePortfolio(portfolioId);
  const [contribution, setContribution] = useState<string | undefined>(undefined);
  const [withdrawal, setWithdrawal] = useState<string | undefined>(undefined);
  const [draft, setDraft] = useState("");
  const [withdrawalDraft, setWithdrawalDraft] = useState("");
  const plan = usePlan(portfolioId, snapshotId, contribution, withdrawal);
  const id = String(portfolioId);

  const apply = (event: FormEvent) => {
    event.preventDefault();
    setContribution(draft || undefined);
    setWithdrawal(withdrawalDraft || undefined);
  };

  if (plan.error instanceof ApiError && plan.error.status === 409) {
    return (
      <div className="grid max-w-xl gap-4">
        <h1 className="text-2xl font-semibold">{t("rebalance.page.title")}</h1>
        <Alert>{plan.error.message}</Alert>
        <Button asChild className="w-fit">
          <Link
            to="/portfolios/$portfolioId/values"
            params={{ portfolioId: id }}
            search={{ rebalance: true }}
          >
            {t("rebalance.page.enterValues")}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold">
          {t("rebalance.page.titleOf", { name: portfolio.data?.name ?? "" })}
        </h1>
        <p className="text-sm text-muted-foreground">{t("rebalance.page.intro")}</p>
      </div>
      <FormError error={plan.error} />
      {plan.data && (
        <>
          {!isToday(plan.data.snapshot_taken_at) && (
            <Alert variant="warning" className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {t("rebalance.page.oldValues", {
                  date: formatDateTime(plan.data.snapshot_taken_at),
                })}
              </span>
              <Button size="sm" variant="outline" asChild>
                <Link
                  to="/portfolios/$portfolioId/values"
                  params={{ portfolioId: id }}
                  search={{ rebalance: true }}
                >
                  {t("rebalance.page.enterValues")}
                </Link>
              </Button>
            </Alert>
          )}
          <form className="flex flex-wrap items-end gap-2" onSubmit={apply}>
            <div className="grid gap-1.5">
              <Label htmlFor="contribution">{t("rebalance.page.contribution")}</Label>
              <Input
                id="contribution"
                inputMode="decimal"
                className="w-40"
                placeholder={plan.data.contribution}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="withdrawal">{t("rebalance.page.withdrawal")}</Label>
              <Input
                id="withdrawal"
                inputMode="decimal"
                className="w-40"
                placeholder={plan.data.withdrawal}
                value={withdrawalDraft}
                aria-describedby="withdrawal-help"
                onChange={(e) => setWithdrawalDraft(e.target.value)}
              />
            </div>
            <Button type="submit" variant="outline">
              {t("rebalance.page.recalculate")}
            </Button>
            <p className="pb-2 text-sm text-muted-foreground">
              {t("rebalance.page.valuesFrom", {
                date: formatDateTime(plan.data.snapshot_taken_at),
                version: plan.data.policy_version_label,
              })}
            </p>
            <p id="withdrawal-help" className="basis-full text-xs text-muted-foreground">
              {t("rebalance.page.withdrawalHelp")}
            </p>
          </form>
          <PlanView plan={plan.data} />
          <div className="no-print">
            <Button variant="outline" asChild>
              <Link
                to="/portfolios/$portfolioId/rebalance/report"
                params={{ portfolioId: id }}
                search={{
                  snapshot: plan.data.snapshot_id,
                  contribution: plan.data.contribution,
                  withdrawal: plan.data.withdrawal,
                }}
              >
                {t("rebalance.page.report")}
              </Link>
            </Button>
          </div>
          {/* Recalculating changes the instructions; the form starts again from them */}
          <ConfirmForm
            key={`${plan.data.snapshot_id}:${plan.data.contribution}:${plan.data.withdrawal}`}
            portfolioId={portfolioId}
            plan={plan.data}
          />
          <Simulation portfolioId={portfolioId} plan={plan.data} />
        </>
      )}
    </div>
  );
}

export function PlanView({ plan, printable = false }: { plan: Plan; printable?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-4">
      <InstructionCards instructions={plan.instructions} precise={plan.precise_amounts} />
      <CashCard
        contribution={plan.contribution}
        withdrawal={plan.withdrawal}
        result={plan.result}
        precise={plan.precise_amounts}
      />
      <CalculationSteps
        contribution={plan.contribution}
        withdrawal={plan.withdrawal}
        result={plan.result}
        precise={plan.precise_amounts}
        open={printable}
      />
      <ResultTable result={plan.result} precise={plan.precise_amounts} open={printable} />
      {/* NFR-15: also on the printed report */}
      <NotAdvice short={t("rebalance.page.notAdvice")} />
    </div>
  );
}

export function InstructionCards({
  instructions,
  precise,
}: {
  instructions: Plan["instructions"];
  precise: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-4 lg:grid-cols-3 print:grid-cols-3">
      {PHASES.map(({ phase, title: phaseTitle }) => {
        const rows = instructions.filter((i) => i.phase === phase);
        const title = rows.some((i) => i.action === WITHDRAWAL_SELL)
          ? t("rebalance.phases.withdrawal")
          : t(`rebalance.phases.${phaseTitle}`);
        return (
          <Card key={phase}>
            <CardHeader>
              <CardTitle>{title}</CardTitle>
            </CardHeader>
            <CardContent>
              {rows.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("rebalance.phases.nothing")}</p>
              ) : (
                <ul className="grid gap-1 text-sm" aria-label={title}>
                  {rows.map((i) => (
                    <li key={i.ticker} className="flex justify-between gap-2">
                      <span>
                        <span className="font-medium">{i.ticker}</span>{" "}
                        <span className="text-muted-foreground">
                          {actionLabel(i.action)}
                          {i.broker && ` · ${i.broker}`}
                        </span>
                      </span>
                      <span className="text-right tabular-nums">
                        {/* RB-24: what to trade, in units where the position has them */}
                        {i.units !== null && (
                          <span className="font-medium">
                            {t("rebalance.units", { units: formatUnits(i.units) })}
                            {" · "}
                          </span>
                        )}
                        {formatAmount(i.amount, precise)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/** Phase 3 withdrawal sells per broker (RB-13, RB-22). */
function withdrawalSellsByBroker(result: Result): [string, number][] {
  const sums = new Map<string, number>();
  for (const p of result.positions) {
    const amount = Number(p.withdrawal_sell);
    if (amount > 0) sums.set(p.broker ?? "", (sums.get(p.broker ?? "") ?? 0) + amount);
  }
  return [...sums];
}

/** RB-09, RB-13: cash calculation, and buys or withdrawal sells per broker. */
export function CashCard({
  contribution,
  withdrawal,
  result: r,
  precise,
}: {
  contribution: string;
  withdrawal: string;
  result: Result;
  precise: boolean;
}) {
  const { t } = useTranslation();
  const toSell = Number(r.total_withdrawal_sells);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("rebalance.cash.title")}</CardTitle>
        <CardDescription>{t("rebalance.cash.description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <dl
          className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm"
          aria-label={t("rebalance.cash.calculation")}
        >
          <dt>{t("rebalance.cash.contribution")}</dt>
          <dd className="text-right tabular-nums">{formatAmount(contribution, precise)}</dd>
          <dt>{t("rebalance.cash.sellProceeds")}</dt>
          <dd className="text-right tabular-nums">
            {formatAmount(r.total_sell_proceeds, precise)}
          </dd>
          <dt>{t("rebalance.cash.withdrawal")}</dt>
          <dd className="text-right tabular-nums">
            {Number(withdrawal) > 0 ? "−" : ""}
            {formatAmount(withdrawal, precise)}
          </dd>
          <dt>{t("rebalance.cash.bufferUsed")}</dt>
          <dd className="text-right tabular-nums">{formatAmount(r.total_buffer_used, precise)}</dd>
          {toSell > 0 ? (
            <>
              <dt className="font-medium">{t("rebalance.cash.toSell")}</dt>
              <dd className="text-right font-medium tabular-nums">
                {formatAmount(r.total_withdrawal_sells, precise)}
              </dd>
            </>
          ) : (
            <>
              <dt className="font-medium">{t("rebalance.cash.available")}</dt>
              <dd className="text-right font-medium tabular-nums">
                {formatAmount(r.available_cash, precise)}
              </dd>
            </>
          )}
          {Number(r.rounding_cash) > 0 && (
            <>
              <dt>{t("rebalance.cash.rounding")}</dt>
              <dd className="text-right tabular-nums">{formatAmount(r.rounding_cash, precise)}</dd>
            </>
          )}
          {Number(r.unallocated_cash) - Number(r.rounding_cash) > 0.005 && (
            <>
              <dt className="text-destructive">{t("rebalance.cash.unallocated")}</dt>
              <dd className="text-right tabular-nums text-destructive">
                {formatAmount(Number(r.unallocated_cash) - Number(r.rounding_cash), precise)}
              </dd>
            </>
          )}
        </dl>
        {toSell > 0 ? (
          <div
            className="grid content-start gap-1 text-sm"
            aria-label={t("rebalance.cash.withdrawalSellsPerBroker")}
          >
            <p className="font-medium">{t("rebalance.cash.withdrawalSellsPerBroker")}</p>
            {withdrawalSellsByBroker(r).map(([broker, amount]) => (
              <p key={broker} className="flex justify-between">
                <span>{broker || t("rebalance.cash.noBroker")}</span>
                <span className="tabular-nums">
                  {formatAmount(amount, precise)} ({formatPct((amount / toSell) * 100)})
                </span>
              </p>
            ))}
          </div>
        ) : (
          <div
            className="grid content-start gap-1 text-sm"
            aria-label={t("rebalance.cash.buysPerBroker")}
          >
            <p className="font-medium">{t("rebalance.cash.buysPerBroker")}</p>
            {Object.entries(r.buys_by_broker).length === 0 && (
              <p className="text-muted-foreground">{t("rebalance.cash.noBuys")}</p>
            )}
            {Object.entries(r.buys_by_broker).map(([broker, amount]) => (
              <p key={broker} className="flex justify-between">
                <span>{broker || t("rebalance.cash.noBroker")}</span>
                <span className="tabular-nums">
                  {formatAmount(amount, precise)} (
                  {formatPct((Number(amount) / Math.max(Number(r.available_cash), 1e-9)) * 100)})
                </span>
              </p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** RB-11, RB-14: every position through all phases, with its distance to target. */
export function ResultTable({
  result,
  precise,
  open = false,
}: {
  result: Result;
  precise: boolean;
  open?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <details open={open}>
      <summary className="cursor-pointer text-sm font-medium">
        {t("rebalance.table.summary")}
      </summary>
      <Table className="mt-2">
        <TableHeader>
          <TableRow>
            <TableHead>{t("rebalance.table.position")}</TableHead>
            <TableHead className="text-right">{t("rebalance.table.target")}</TableHead>
            <TableHead className="text-right">{t("rebalance.table.before")}</TableHead>
            <TableHead>{t("rebalance.table.phase1")}</TableHead>
            <TableHead className="text-right">{t("rebalance.table.afterPhase1")}</TableHead>
            <TableHead>{t("rebalance.table.phase3")}</TableHead>
            <TableHead className="text-right">{t("rebalance.table.after")}</TableHead>
            <TableHead className="text-right">{t("rebalance.table.toTarget")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result.positions.map((p) => {
            const diff =
              p.difference_to_target_pct === null ? null : Number(p.difference_to_target_pct);
            return (
              <TableRow key={p.ticker}>
                <TableCell>
                  <span className="font-medium">{p.ticker}</span>
                  {p.broker && <span className="text-muted-foreground"> · {p.broker}</span>}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {p.target_pct === null ? "–" : formatPct(p.target_pct)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatAmount(p.value_before, precise)} ({formatPct(p.allocation_before_pct)})
                  <Units units={p.units_before} />
                </TableCell>
                <TableCell>
                  {actionLabel(p.phase1_action)}
                  {Number(p.sell_amount) > 0 && ` −${formatAmount(p.sell_amount, precise)}`}
                  {Number(p.buffer_buy) > 0 && ` +${formatAmount(p.buffer_buy, precise)}`}
                  {Number(p.buffer_deployed) > 0 && ` −${formatAmount(p.buffer_deployed, precise)}`}
                  {Number(p.sell_amount) > 0 && <Units units={p.sell_units} />}
                  {Number(p.buffer_buy) > 0 && <Units units={p.buffer_buy_units} />}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatPct(p.allocation_after_phase1_pct)}
                </TableCell>
                <TableCell>
                  {actionLabel(p.phase3_action)}
                  {Number(p.buy_amount) > 0 && ` +${formatAmount(p.buy_amount, precise)}`}
                  {Number(p.withdrawal_sell) > 0 && ` −${formatAmount(p.withdrawal_sell, precise)}`}
                  {Number(p.buy_amount) > 0 && <Units units={p.buy_units} />}
                  {Number(p.withdrawal_sell) > 0 && <Units units={p.withdrawal_sell_units} />}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatAmount(p.value_after, precise)} ({formatPct(p.allocation_after_pct)})
                  <Units units={p.units_after} />
                </TableCell>
                <TableCell
                  className="text-right tabular-nums"
                  aria-label={
                    diff === null
                      ? t("rebalance.table.notInPolicy")
                      : t(
                          diff >= 0 ? "rebalance.table.aboveTarget" : "rebalance.table.belowTarget",
                          {
                            pct: formatPct(Math.abs(diff)),
                          },
                        )
                  }
                >
                  {diff === null ? "–" : <DistanceIndicator diff={diff} />}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </details>
  );
}

/** RB-24: units below an amount; nothing for positions without units. */
function Units({ units }: { units: string | null }) {
  const { t } = useTranslation();
  if (units === null) return null;
  return (
    <span className="block text-xs text-muted-foreground">
      {t("rebalance.units", { units: formatUnits(units) })}
    </span>
  );
}

// Symbols, not text: the same in every language
const ABOVE = "▲";
const BELOW = "▼";

/** RB-14: above (▲), at (=) or below (▼) target after all actions. */
function DistanceIndicator({ diff }: { diff: number }) {
  const { t } = useTranslation();
  if (Math.abs(diff) < 0.05) return <span>{t("rebalance.table.atTarget")}</span>;
  return (
    <span>
      {diff > 0 ? ABOVE : BELOW} {formatPct(Math.abs(diff))}
    </span>
  );
}

/** RB-16: units and amounts as executed, pre-filled with the calculated ones. */
function ConfirmForm({ portfolioId, plan }: { portfolioId: number; plan: Plan }) {
  const { t } = useTranslation();
  const confirm = useConfirm(portfolioId);
  const navigate = useNavigate();
  const key = (phase: string, ticker: string) => `${phase}:${ticker}`;
  const [executed, setExecuted] = useState<Record<string, string>>(() =>
    Object.fromEntries(plan.instructions.map((i) => [key(i.phase, i.ticker), i.amount])),
  );
  const [executedUnits, setExecutedUnits] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      plan.instructions.flatMap((i) =>
        i.units === null ? [] : [[key(i.phase, i.ticker), i.units]],
      ),
    ),
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    confirm.mutate(
      {
        snapshot_id: plan.snapshot_id,
        contribution: plan.contribution,
        withdrawal: plan.withdrawal,
        policy_version_id: plan.policy_version_id,
        executed: plan.instructions.map((i) => ({
          phase: i.phase,
          ticker: i.ticker,
          amount: executed[key(i.phase, i.ticker)] || "0",
          ...(i.units !== null && { units: executedUnits[key(i.phase, i.ticker)] || "0" }),
        })),
      },
      {
        onSuccess: (r) =>
          navigate({ to: "/rebalances/$rebalanceId", params: { rebalanceId: String(r.id) } }),
      },
    );
  };

  if (plan.instructions.length === 0) return <Alert>{t("rebalance.confirm.nothing")}</Alert>;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("rebalance.confirm.title")}</CardTitle>
        <CardDescription>{t("rebalance.confirm.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3" onSubmit={submit}>
          <div className="grid gap-2 lg:grid-cols-2">
            {plan.instructions.map((i) => {
              const k = key(i.phase, i.ticker);
              const names = { action: actionLabel(i.action), ticker: i.ticker };
              return (
                <div key={k} className="grid grid-cols-[1fr_6rem_8rem] items-center gap-2 text-sm">
                  <span>
                    {i.ticker}{" "}
                    <span className="text-muted-foreground">{actionLabel(i.action)}</span>
                  </span>
                  {i.units === null ? (
                    <span />
                  ) : (
                    <Input
                      aria-label={t("rebalance.confirm.executedUnits", names)}
                      placeholder={t("rebalance.confirm.units")}
                      inputMode="decimal"
                      value={executedUnits[k]}
                      onChange={(e) => setExecutedUnits({ ...executedUnits, [k]: e.target.value })}
                    />
                  )}
                  <Input
                    aria-label={t("rebalance.confirm.executed", names)}
                    placeholder={t("rebalance.confirm.amount")}
                    inputMode="decimal"
                    value={executed[k]}
                    onChange={(e) => setExecuted({ ...executed, [k]: e.target.value })}
                  />
                </div>
              );
            })}
          </div>
          <FormError error={confirm.error} />
          <div className="flex justify-end">
            <Button type="submit" disabled={confirm.isPending}>
              {t("rebalance.confirm.submit")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/** RB-20: N cycles with the same contribution and withdrawal and unchanged prices; nothing
 * stored. */
function Simulation({ portfolioId, plan }: { portfolioId: number; plan: Plan }) {
  const { t } = useTranslation();
  const simulate = useSimulation(portfolioId);
  const [cycles, setCycles] = useState("12");
  const precise = plan.precise_amounts;
  const last = simulate.data?.at(-1);
  return (
    <details>
      <summary className="cursor-pointer text-sm font-medium">
        {t("rebalance.simulation.summary")}
      </summary>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          simulate.mutate({
            cycles: Number(cycles),
            contribution: plan.contribution,
            withdrawal: plan.withdrawal,
            snapshot_id: plan.snapshot_id,
          });
        }}
      >
        <div className="grid gap-1.5">
          <Label htmlFor="cycles">{t("rebalance.simulation.cycles")}</Label>
          <Input
            id="cycles"
            type="number"
            min={1}
            max={120}
            className="w-24"
            value={cycles}
            onChange={(e) => setCycles(e.target.value)}
          />
        </div>
        <Button type="submit" variant="outline">
          {t("rebalance.simulation.submit")}
        </Button>
        <p className="pb-2 text-sm text-muted-foreground">
          {t("rebalance.simulation.perCycle", {
            contribution: formatAmount(plan.contribution, precise),
            withdrawal: formatAmount(plan.withdrawal, precise),
          })}
        </p>
      </form>
      <FormError error={simulate.error} />
      {simulate.data && last && (
        <div className="mt-3 grid gap-3">
          <Table aria-label={t("rebalance.simulation.table")}>
            <TableHeader>
              <TableRow>
                <TableHead>{t("rebalance.simulation.cycle")}</TableHead>
                <TableHead className="text-right">{t("rebalance.simulation.sold")}</TableHead>
                <TableHead className="text-right">{t("rebalance.simulation.bought")}</TableHead>
                <TableHead className="text-right">{t("rebalance.simulation.valueAfter")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {simulate.data.map((c, n) => (
                <TableRow key={n}>
                  <TableCell>{n + 1}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatAmount(
                      Number(c.total_sell_proceeds) + Number(c.total_withdrawal_sells),
                      precise,
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatAmount(
                      Number(c.available_cash) -
                        Number(c.unallocated_cash) +
                        Number(c.total_buffer_used),
                      precise,
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatAmount(c.total_value_after, precise)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="text-sm font-medium">
            {t("rebalance.simulation.afterCycle", { cycle: simulate.data.length })}
          </p>
          <ul className="grid gap-1 text-sm">
            {last.positions.map((p) => (
              <li key={p.ticker} className="flex justify-between gap-2">
                <span>{p.ticker}</span>
                <span className="tabular-nums">
                  {formatPct(p.allocation_after_pct)}
                  {p.target_pct !== null && (
                    <span className="text-muted-foreground">
                      {t("rebalance.simulation.target", { pct: formatPct(p.target_pct) })}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  );
}
