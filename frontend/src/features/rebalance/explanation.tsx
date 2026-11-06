import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { formatAmount, formatPct } from "@/lib/format";

import type { Result } from "./api";

type Position = Result["positions"][number];

/** RB-23: the calculation step by step, with the amounts of this rebalance. */
export function CalculationSteps({
  contribution,
  withdrawal,
  result: r,
  precise,
  open = false,
}: {
  contribution: string;
  withdrawal: string;
  result: Result;
  precise: boolean;
  open?: boolean;
}) {
  const { t } = useTranslation();
  const amount = (value: string | number) => formatAmount(value, precise);
  const positive = (value: string) => Number(value) > 0;

  const dips = r.positions.filter((p) => positive(p.buffer_buy));
  const sells = r.positions.filter((p) => positive(p.sell_amount));
  const buys = r.positions.filter((p) => positive(p.buy_amount));
  const withdrawalSells = r.positions.filter((p) => positive(p.withdrawal_sell));
  const final = Number(r.total_value_before) + Number(contribution) - Number(withdrawal);
  const cash = Number(contribution) + Number(r.total_sell_proceeds) - Number(withdrawal);

  const sellText = (p: Position) => {
    const values = { amount: amount(p.sell_amount) };
    if (!p.in_policy) return t("rebalance.explanation.sells.notInPolicy", values);
    if (p.exit) return t("rebalance.explanation.sells.exit", values);
    return t("rebalance.explanation.sells.threshold", {
      ...values,
      before: formatPct(p.allocation_before_pct),
      // A position sold to its midband gets nothing in phase 3, so it ends exactly there
      after: formatPct(p.allocation_after_pct),
    });
  };
  const afterPhase3 = (p: Position, value: string) => ({
    amount: amount(value),
    after: formatPct(p.allocation_after_pct),
    target: p.target_pct === null ? "–" : formatPct(p.target_pct),
  });

  return (
    <details open={open}>
      <summary className="cursor-pointer text-sm font-medium">
        {t("rebalance.explanation.title")}
      </summary>
      <div className="mt-2 grid gap-3 text-sm">
        <p>
          {t("rebalance.explanation.finalValue", {
            before: amount(r.total_value_before),
            contribution: amount(contribution),
            withdrawal: amount(withdrawal),
            final: amount(final),
          })}
        </p>
        <ol className="grid list-decimal gap-3 pl-5">
          <Step title={t("rebalance.explanation.dips.title")}>
            {dips.length === 0 ? (
              <p>{t("rebalance.explanation.dips.none")}</p>
            ) : (
              <>
                <p>
                  {t("rebalance.explanation.dips.intro", { amount: amount(r.total_buffer_used) })}
                </p>
                <Items
                  rows={dips.map((p) => [
                    p.ticker,
                    t("rebalance.explanation.dips.item", { amount: amount(p.buffer_buy) }),
                  ])}
                />
              </>
            )}
          </Step>
          <Step title={t("rebalance.explanation.sells.title")}>
            {sells.length === 0 ? (
              <p>{t("rebalance.explanation.sells.none")}</p>
            ) : (
              <Items rows={sells.map((p) => [p.ticker, sellText(p)])} />
            )}
          </Step>
          <Step title={t("rebalance.explanation.cash.title")}>
            <p>
              {t("rebalance.explanation.cash.sum", {
                contribution: amount(contribution),
                sells: amount(r.total_sell_proceeds),
                withdrawal: amount(withdrawal),
                cash: amount(cash),
              })}{" "}
              {positive(r.total_withdrawal_sells)
                ? t("rebalance.explanation.cash.missing", {
                    amount: amount(r.total_withdrawal_sells),
                  })
                : positive(r.available_cash)
                  ? t("rebalance.explanation.cash.available")
                  : t("rebalance.explanation.cash.nothing")}
            </p>
          </Step>
          {withdrawalSells.length > 0 ? (
            <Step title={t("rebalance.explanation.withdrawal.title")}>
              <p>
                {t("rebalance.explanation.withdrawal.intro", {
                  amount: amount(r.total_withdrawal_sells),
                })}
              </p>
              <Items
                rows={withdrawalSells.map((p) => [
                  p.ticker,
                  t("rebalance.explanation.withdrawal.item", afterPhase3(p, p.withdrawal_sell)),
                ])}
              />
            </Step>
          ) : (
            <Step title={t("rebalance.explanation.buys.title")}>
              {buys.length === 0 ? (
                <p>{t("rebalance.explanation.buys.none")}</p>
              ) : (
                <>
                  <p>{t("rebalance.explanation.buys.intro")}</p>
                  <Items
                    rows={buys.map((p) => [
                      p.ticker,
                      t("rebalance.explanation.buys.item", afterPhase3(p, p.buy_amount)),
                    ])}
                  />
                </>
              )}
              {/* RB-24: what rounding to whole units leaves is not an error */}
              {positive(r.rounding_cash) && (
                <p>
                  {t("rebalance.explanation.buys.rounding", { amount: amount(r.rounding_cash) })}
                </p>
              )}
              {Number(r.unallocated_cash) - Number(r.rounding_cash) > 0.005 && (
                <p className="text-destructive">
                  {t("rebalance.explanation.buys.unallocated", {
                    amount: amount(Number(r.unallocated_cash) - Number(r.rounding_cash)),
                  })}
                </p>
              )}
            </Step>
          )}
        </ol>
      </div>
    </details>
  );
}

function Step({ title, children }: { title: string; children: ReactNode }) {
  return (
    <li className="grid gap-1">
      <span className="font-medium">{title}</span>
      {children}
    </li>
  );
}

function Items({ rows }: { rows: [string, string][] }) {
  return (
    <ul className="grid gap-0.5">
      {rows.map(([ticker, text]) => (
        <li key={ticker}>
          <span className="font-medium">{ticker}</span> {text}
        </li>
      ))}
    </ul>
  );
}
