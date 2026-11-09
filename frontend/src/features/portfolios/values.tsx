import { useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { ASSET_TYPES, typeLabel } from "@/components/charts";
import { AutoPriceInfo, PriceNotice, type AutoPrice } from "@/features/prices/auto-price";
import { PriceSourceControl } from "@/features/prices/price-source";
import { formatAmount } from "@/lib/format";

import {
  usePortfolio,
  usePortfolioActions,
  usePrefill,
  useSnapshots,
  type PrefillRow,
  type ValueIn,
} from "./api";

interface Row {
  ticker: string;
  name: string;
  type: string;
  units: string;
  price: string;
  value: string;
  /** Where the price comes from: the auto price of the price source, or what the investor
   * entered last: the price (value follows) or the value (price follows). */
  entered: "auto" | "price" | "value";
  /** The auto price of the position's price source, if it has one (CMP-01), and that price
   * in the portfolio currency, as pre-filled. */
  auto: AutoPrice | null;
  autoPrice: string;
  /** Why an auto source has no price (PRC-09, PRC-11), and its listing. */
  notice: string | null;
  listingSymbol: string | null;
  /** The previous value of a position whose units are not known yet (CMP-10). */
  unknownUnitsValue: string | null;
  inPolicy: boolean;
  isNew: boolean;
}

const CASH_BUFFER = "cash_buffer";
const FIELDS = ["ticker", "units", "price", "value"] as const;

function fromPrefill(r: PrefillRow): Row {
  const cash = r.type === CASH_BUFFER;
  return {
    ticker: r.ticker,
    name: r.name,
    type: r.type,
    units: r.units ?? "",
    price: r.price ?? "",
    value: cash ? r.value : "",
    entered: cash ? "value" : r.auto ? "auto" : "price",
    auto: cash ? null : r.auto,
    autoPrice: r.auto ? (r.price ?? "") : "",
    notice: cash ? null : r.notice,
    listingSymbol: r.listing_symbol,
    unknownUnitsValue: !cash && r.units === null ? r.value : null,
    inPolicy: r.in_policy,
    isNew: false,
  };
}

/** Shown in the field that follows from the others; empty while it cannot be calculated. */
function derived(row: Row): { price: string; value: string } {
  const units = Number(row.units);
  if (row.units === "" || Number.isNaN(units)) return { price: row.price, value: row.value };
  if (row.entered !== "value") {
    const price = Number(row.price);
    const value = row.price === "" || Number.isNaN(price) ? "" : (units * price).toFixed(2);
    return { price: row.price, value };
  }
  const value = Number(row.value);
  const price =
    row.value === "" || Number.isNaN(value) || units === 0
      ? ""
      : // Shown only; the value is sent. 10 significant digits, for small crypto prices too
        String(Number((value / units).toPrecision(10)));
  return { price, value: row.value };
}

/** What is sent: units with the price or the value; without both, the backend uses the auto
 * price, or the price last entered (CMP-01). The cash buffer has only its amount. */
function toValueIn(row: Row): ValueIn {
  const known = row.isNew ? { name: row.name, type: row.type } : {};
  if (row.type === CASH_BUFFER) return { ticker: row.ticker, value: row.value || "0", ...known };
  return {
    ticker: row.ticker,
    units: row.units === "" ? null : row.units,
    ...(row.entered === "price" && row.price !== "" && { price: row.price }),
    ...(row.entered === "value" && row.value !== "" && { value: row.value }),
    ...known,
  };
}

/** CMP-01, CMP-02, CMP-06: enter units and prices; saved with the exact time. The only
 * place where values are entered (RB-02); a rebalance uses the latest snapshot. */
export function EnterValuesPage({ portfolioId }: { portfolioId: number }) {
  const { t } = useTranslation();
  const prefill = usePrefill(portfolioId);
  const portfolio = usePortfolio(portfolioId);
  if (!prefill.data || !portfolio.data)
    return <p className="text-muted-foreground">{t("common.loading")}</p>;
  return (
    <ValuesForm
      portfolioId={portfolioId}
      name={portfolio.data.name}
      currency={portfolio.data.currency}
      initial={prefill.data.map(fromPrefill)}
    />
  );
}

function ValuesForm({
  portfolioId,
  name,
  currency,
  initial,
}: {
  portfolioId: number;
  name: string;
  currency: string;
  initial: Row[];
}) {
  const { t } = useTranslation();
  const { snapshot } = usePortfolioActions(portfolioId);
  const snapshots = useSnapshots(portfolioId);
  const navigate = useNavigate();
  const [rows, setRows] = useState(initial);
  const [correction, setCorrection] = useState(false);
  const latestId = snapshots.data?.[0]?.id ?? null;
  const update = (i: number, patch: Partial<Row>) =>
    setRows((r) => r.map((row, k) => (k === i ? { ...row, ...patch } : row)));
  const problem = (i: number, field: string) =>
    snapshot.error instanceof ApiError
      ? snapshot.error.problems.find((p) => p.path === `values[${i}].${field}`)?.message
      : undefined;
  const rowProblems = (i: number) =>
    FIELDS.map((field) => problem(i, field)).filter((p) => p !== undefined);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    snapshot.mutate(
      { values: rows.map(toValueIn), corrects_snapshot_id: correction ? latestId : null },
      {
        onSuccess: (s) =>
          navigate({ to: "/snapshots/$snapshotId", params: { snapshotId: String(s.id) } }),
      },
    );
  };

  return (
    <form className="grid max-w-4xl gap-4" onSubmit={submit}>
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold">{t("portfolios.values.title", { name })}</h1>
        <p className="text-sm text-muted-foreground">
          {t("portfolios.values.description", { currency })}
        </p>
      </div>
      <div className="grid gap-3">
        <div
          aria-hidden
          className="hidden gap-2 text-xs font-medium text-muted-foreground sm:grid sm:grid-cols-[1fr_7rem_8rem_9rem]"
        >
          <span>{t("portfolios.values.position")}</span>
          <span>{t("portfolios.values.units")}</span>
          <span>{t("portfolios.values.price", { currency })}</span>
          <span>{t("portfolios.values.value", { currency })}</span>
        </div>
        {rows.map((r, i) => {
          const cash = r.type === CASH_BUFFER;
          const shown = derived(r);
          const label = r.ticker || null;
          return (
            <div key={i} className="grid gap-1">
              <div className="grid gap-2 sm:grid-cols-[1fr_7rem_8rem_9rem] sm:items-center">
                {r.isNew ? (
                  <div className="grid grid-cols-3 gap-2">
                    <Input
                      aria-label={t("portfolios.values.newTicker")}
                      value={r.ticker}
                      onChange={(e) => update(i, { ticker: e.target.value })}
                      required
                    />
                    <Input
                      aria-label={t("portfolios.values.newName")}
                      value={r.name}
                      onChange={(e) => update(i, { name: e.target.value })}
                      placeholder={t("portfolios.values.namePlaceholder")}
                    />
                    <NativeSelect
                      aria-label={t("portfolios.values.newType")}
                      value={r.type}
                      onChange={(e) =>
                        update(i, {
                          type: e.target.value,
                          entered: e.target.value === CASH_BUFFER ? "value" : r.entered,
                        })
                      }
                    >
                      {ASSET_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {typeLabel(type)}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                ) : (
                  <span className="text-sm">
                    <span className="font-medium">{r.ticker}</span>{" "}
                    <span className="text-muted-foreground">{r.name}</span>
                    {!r.inPolicy && (
                      <span className="text-muted-foreground">
                        {t("portfolios.values.notInPolicy")}
                      </span>
                    )}
                  </span>
                )}
                {/* On phones the three fields share one row; from sm on they are columns */}
                <div className="grid grid-cols-3 gap-2 sm:contents">
                  {cash ? (
                    <span className="col-span-2 self-center text-xs text-muted-foreground">
                      {t("portfolios.values.cash")}
                    </span>
                  ) : (
                    <>
                      <Input
                        aria-label={
                          label
                            ? t("portfolios.values.unitsOf", { ticker: label })
                            : t("portfolios.values.unitsOfNew")
                        }
                        inputMode="decimal"
                        value={r.units}
                        onChange={(e) => update(i, { units: e.target.value })}
                      />
                      <Input
                        aria-label={
                          label
                            ? t("portfolios.values.priceOf", { ticker: label })
                            : t("portfolios.values.priceOfNew")
                        }
                        inputMode="decimal"
                        value={shown.price}
                        onChange={(e) => update(i, { price: e.target.value, entered: "price" })}
                      />
                    </>
                  )}
                  <Input
                    aria-label={
                      label
                        ? t("portfolios.values.valueOf", { ticker: label })
                        : t("portfolios.values.valueOfNew")
                    }
                    inputMode="decimal"
                    value={shown.value}
                    onChange={(e) => update(i, { value: e.target.value, entered: "value" })}
                  />
                </div>
              </div>
              {/* PRC-02: positions without a price source are looked up */}
              {!cash && r.ticker.trim() && (
                <PriceSourceControl
                  ticker={r.ticker}
                  name={r.isNew ? r.name : undefined}
                  type={r.isNew ? r.type : undefined}
                  onName={(name) => r.isNew && update(i, { name })}
                />
              )}
              {r.entered === "auto" && r.auto && (
                <AutoPriceInfo auto={r.auto} currency={currency} />
              )}
              {r.entered !== "auto" && r.auto && (
                <p className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {t("prices.auto.changed")}
                  <button
                    type="button"
                    className="underline"
                    onClick={() => update(i, { entered: "auto", price: r.autoPrice, value: "" })}
                  >
                    {t("prices.auto.useAuto")}
                  </button>
                </p>
              )}
              {r.notice && <PriceNotice notice={r.notice} symbol={r.listingSymbol} />}
              {r.unknownUnitsValue !== null && (
                <p className="text-xs text-muted-foreground">
                  {t("portfolios.values.unitsUnknown", {
                    value: formatAmount(r.unknownUnitsValue, true),
                  })}
                </p>
              )}
              {rowProblems(i).map((message) => (
                <p key={message} className="text-xs text-destructive">
                  {message}
                </p>
              ))}
            </div>
          );
        })}
      </div>
      <div>
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            setRows((r) => [
              ...r,
              {
                ticker: "",
                name: "",
                type: "stock",
                units: "",
                price: "",
                value: "",
                entered: "price",
                auto: null,
                autoPrice: "",
                notice: null,
                listingSymbol: null,
                unknownUnitsValue: null,
                inPolicy: false,
                isNew: true,
              },
            ])
          }
        >
          {t("portfolios.values.add")}
        </Button>
      </div>
      {latestId !== null && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={correction}
            onChange={(e) => setCorrection(e.target.checked)}
          />
          {t("portfolios.values.correction")}
        </label>
      )}
      <FormError
        error={snapshot.error}
        fields={rows.flatMap((_, i) => FIELDS.map((field) => `values[${i}].${field}`))}
      />
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() =>
            navigate({
              to: "/portfolios/$portfolioId",
              params: { portfolioId: String(portfolioId) },
            })
          }
        >
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={snapshot.isPending}>
          {t("portfolios.values.save")}
        </Button>
      </div>
    </form>
  );
}
