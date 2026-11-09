import i18n from "i18next";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";

// --- Bars per position: real allocation against target and band (CMP-07) ---------

export interface AllocationRow {
  ticker: string;
  name: string;
  allocation: number;
  target: number | null;
  buyAbs: number | null;
  sellAbs: number | null;
  status: string;
}

const BAND_STATUSES = [
  "below_buy_threshold",
  "within_band",
  "above_sell_threshold",
  "not_in_policy",
] as const;
type BandStatus = (typeof BAND_STATUSES)[number];

/** The band status in the current language; unknown values as sent. */
export function statusText(status: string): string {
  return (BAND_STATUSES as readonly string[]).includes(status)
    ? i18n.t(`portfolios.bandStatus.${status as BandStatus}`)
    : status;
}

function describe(row: AllocationRow): string {
  const parts = [
    i18n.t("portfolios.charts.ofPortfolio", {
      ticker: row.ticker,
      allocation: formatPct(row.allocation),
    }),
  ];
  if (row.target !== null) {
    parts.push(i18n.t("portfolios.charts.target", { target: formatPct(row.target) }));
    parts.push(
      i18n.t("portfolios.charts.band", {
        from: formatPct(row.buyAbs ?? 0),
        to: formatPct(row.sellAbs ?? 0),
      }),
    );
  }
  parts.push(statusText(row.status));
  return parts.join(", ");
}

export function AllocationBars({ rows }: { rows: AllocationRow[] }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<string | null>(null);
  const max =
    Math.max(1, ...rows.map((r) => Math.max(r.allocation, r.sellAbs ?? 0, r.target ?? 0))) * 1.08;
  const pct = (v: number) => `${(Math.min(v, max) / max) * 100}%`;

  return (
    <figure className="grid gap-2" aria-label={t("portfolios.charts.byPosition")}>
      <ul className="grid gap-2">
        {rows.map((r) => (
          <li key={r.ticker} className="grid grid-cols-[4.5rem_1fr] items-center gap-2">
            <span className="truncate text-sm font-medium" title={r.name}>
              {r.ticker}
            </span>
            <div
              className="relative h-7 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              tabIndex={0}
              role="img"
              aria-label={describe(r)}
              onPointerEnter={() => setActive(r.ticker)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(r.ticker)}
              onBlur={() => setActive(null)}
            >
              {r.buyAbs !== null && r.sellAbs !== null && (
                <div
                  className="absolute inset-y-0 bg-[var(--band)]"
                  style={{
                    left: pct(r.buyAbs),
                    width: `calc(${pct(r.sellAbs)} - ${pct(r.buyAbs)})`,
                  }}
                  data-testid={`band-${r.ticker}`}
                />
              )}
              <div
                className={cn(
                  "absolute left-0 top-1/2 h-5 -translate-y-1/2 rounded-r-[4px] bg-[var(--series-1)] transition-opacity",
                  active === r.ticker && "opacity-80",
                )}
                style={{ width: pct(r.allocation) }}
              />
              {r.target !== null && (
                <div
                  className="absolute inset-y-0 w-0.5 bg-foreground"
                  style={{ left: pct(r.target) }}
                  data-testid={`target-${r.ticker}`}
                />
              )}
              <span
                className="absolute top-1/2 -translate-y-1/2 pl-1.5 text-xs tabular-nums"
                style={{ left: pct(r.allocation) }}
              >
                {formatPct(r.allocation)}
              </span>
              {active === r.ticker && (
                <div
                  role="tooltip"
                  className="absolute bottom-full left-0 z-10 mb-1 rounded-md border bg-card px-2 py-1 text-xs shadow-md"
                >
                  <strong className="block">{formatPct(r.allocation)}</strong>
                  <span className="text-muted-foreground">{describe(r)}</span>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
      <figcaption className="flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-4 rounded-sm bg-[var(--series-1)]" aria-hidden />{" "}
          {t("portfolios.charts.allocation")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-0.5 bg-foreground" aria-hidden />{" "}
          {t("portfolios.charts.targetLegend")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-4 bg-[var(--band)]" aria-hidden />{" "}
          {t("portfolios.charts.bandLegend")}
        </span>
      </figcaption>
    </figure>
  );
}

// --- Before and after a rebalance, per position (RB-27) --------------------------

export interface BeforeAfterRow {
  ticker: string;
  name: string;
  before: number;
  after: number;
  target: number | null;
}

function describeBeforeAfter(row: BeforeAfterRow): string {
  const parts = [
    i18n.t("rebalance.preview.of", {
      ticker: row.ticker,
      before: formatPct(row.before),
      after: formatPct(row.after),
    }),
  ];
  if (row.target !== null) {
    parts.push(i18n.t("portfolios.charts.target", { target: formatPct(row.target) }));
  }
  return parts.join(", ");
}

function ShareBar({
  id,
  value,
  pct,
  className,
}: {
  id: string;
  value: number;
  pct: (v: number) => string;
  className: string;
}) {
  return (
    <div className="relative h-3.5" data-testid={id}>
      <div className={cn("h-full rounded-r-[4px]", className)} style={{ width: pct(value) }} />
      <span
        className="absolute top-1/2 -translate-y-1/2 pl-1.5 text-xs tabular-nums"
        style={{ left: pct(value) }}
      >
        {formatPct(value)}
      </span>
    </div>
  );
}

/** Share of the portfolio per position before and after the rebalance, with the target. */
export function BeforeAfterBars({ rows }: { rows: BeforeAfterRow[] }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<string | null>(null);
  const max = Math.max(1, ...rows.map((r) => Math.max(r.before, r.after, r.target ?? 0))) * 1.08;
  const pct = (v: number) => `${(Math.min(v, max) / max) * 100}%`;

  return (
    <figure className="grid gap-2" aria-label={t("rebalance.preview.chart")}>
      <ul className="grid gap-2">
        {rows.map((r) => (
          <li key={r.ticker} className="grid grid-cols-[4.5rem_1fr] items-center gap-2">
            <span className="truncate text-sm font-medium" title={r.name}>
              {r.ticker}
            </span>
            <div
              className="relative grid h-9 content-center gap-0.5 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              tabIndex={0}
              role="img"
              aria-label={describeBeforeAfter(r)}
              onPointerEnter={() => setActive(r.ticker)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(r.ticker)}
              onBlur={() => setActive(null)}
            >
              <ShareBar
                id={`before-${r.ticker}`}
                value={r.before}
                pct={pct}
                className="bg-muted-foreground/40"
              />
              <ShareBar
                id={`after-${r.ticker}`}
                value={r.after}
                pct={pct}
                className="bg-[var(--series-1)]"
              />
              {r.target !== null && (
                <div
                  className="absolute inset-y-0 w-0.5 bg-foreground"
                  style={{ left: pct(r.target) }}
                  data-testid={`target-${r.ticker}`}
                />
              )}
              {active === r.ticker && (
                <div
                  role="tooltip"
                  className="absolute bottom-full left-0 z-10 mb-1 rounded-md border bg-card px-2 py-1 text-xs shadow-md"
                >
                  <span className="text-muted-foreground">{describeBeforeAfter(r)}</span>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
      <figcaption className="flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-4 rounded-sm bg-muted-foreground/40" aria-hidden />{" "}
          {t("rebalance.preview.before")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-4 rounded-sm bg-[var(--series-1)]" aria-hidden />{" "}
          {t("rebalance.preview.after")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-0.5 bg-foreground" aria-hidden />{" "}
          {t("portfolios.charts.targetLegend")}
        </span>
      </figcaption>
    </figure>
  );
}

// --- Pie by type (CMP-07) --------------------------------------------------------

// Colour follows the type, never its rank (fixed slots)
const TYPE_SLOT: Record<string, string> = {
  ETF: "var(--series-1)",
  stock: "var(--series-2)",
  crypto: "var(--series-3)",
  cash_buffer: "var(--series-4)",
};
export const ASSET_TYPES = ["ETF", "stock", "crypto", "cash_buffer"] as const;

/** The asset type in the current language; unknown types as sent. */
export function typeLabel(type: string): string {
  return (ASSET_TYPES as readonly string[]).includes(type)
    ? i18n.t(`domain.assetType.${type as (typeof ASSET_TYPES)[number]}`)
    : type;
}

export interface TypeShare {
  type: string;
  value: number;
}

function arc(start: number, end: number, r: number): string {
  const point = (a: number) => [r + r * Math.sin(a), r - r * Math.cos(a)];
  const [x0, y0] = point(start);
  const [x1, y1] = point(end);
  const large = end - start > Math.PI ? 1 : 0;
  return `M ${r} ${r} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;
}

export function TypePie({ shares, size = 160 }: { shares: TypeShare[]; size?: number }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<string | null>(null);
  const order = Object.keys(TYPE_SLOT);
  const parts = shares
    .filter((s) => s.value > 0)
    .sort((a, b) => order.indexOf(a.type) - order.indexOf(b.type));
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  if (total === 0)
    return <p className="text-sm text-muted-foreground">{t("portfolios.charts.noValues")}</p>;
  const r = size / 2;
  const slices = parts.reduce<(TypeShare & { share: number; start: number; end: number })[]>(
    (acc, p) => {
      const start = acc.at(-1)?.end ?? 0;
      const share = p.value / total;
      return [...acc, { ...p, share, start, end: start + share * 2 * Math.PI }];
    },
    [],
  );
  const label = (s: (typeof slices)[number]) =>
    t("portfolios.charts.typeShare", { type: typeLabel(s.type), share: formatPct(s.share * 100) });

  return (
    <figure
      className="flex flex-wrap items-center gap-6"
      aria-label={t("portfolios.charts.byType")}
    >
      <div className="relative">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {slices.map((s) =>
            s.share >= 0.9999 ? (
              <circle
                key={s.type}
                cx={r}
                cy={r}
                r={r}
                fill={TYPE_SLOT[s.type]}
                tabIndex={0}
                role="img"
                aria-label={label(s)}
                onFocus={() => setActive(s.type)}
                onBlur={() => setActive(null)}
                onPointerEnter={() => setActive(s.type)}
                onPointerLeave={() => setActive(null)}
              />
            ) : (
              <path
                key={s.type}
                d={arc(s.start, s.end, r)}
                fill={TYPE_SLOT[s.type] ?? "var(--muted-foreground)"}
                // 2px gap in the surface colour between slices
                stroke="var(--background)"
                strokeWidth={2}
                strokeLinejoin="round"
                tabIndex={0}
                role="img"
                aria-label={label(s)}
                className={cn("outline-none transition-opacity", active === s.type && "opacity-80")}
                onPointerEnter={() => setActive(s.type)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(s.type)}
                onBlur={() => setActive(null)}
              />
            ),
          )}
        </svg>
        {active && (
          <div
            role="tooltip"
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-md border bg-card px-2 py-1 text-xs shadow-md"
          >
            {label(slices.find((s) => s.type === active)!)}
          </div>
        )}
      </div>
      <figcaption>
        <ul className="grid gap-1 text-sm">
          {slices.map((s) => (
            <li key={s.type} className="flex items-center gap-2">
              <span
                className="inline-block size-3 rounded-sm"
                style={{ background: TYPE_SLOT[s.type] }}
                aria-hidden
              />
              <span>{typeLabel(s.type)}</span>
              <span className="tabular-nums text-muted-foreground">{formatPct(s.share * 100)}</span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}
