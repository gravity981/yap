import { useState } from "react";
import { useTranslation } from "react-i18next";

import { formatDate, formatPct } from "@/lib/format";

import type { SnapshotListItem as Listed } from "./api";

interface Series {
  key: string;
  label: string;
  color: string;
  dash?: string;
  values: number[]; // per snapshot, oldest first; 0 where the position was not held
}

const W = 560;
const H = 200;
const PAD = { left: 36, right: 16, top: 12, bottom: 24 };
const OTHER = "\u0000other";
// Four categorical colours; dashes tell the lines apart without the colour (WCAG 1.4.1)
const STYLES = [
  { color: "var(--series-1)" },
  { color: "var(--series-2)", dash: "6 3" },
  { color: "var(--series-3)", dash: "2 3" },
  { color: "var(--series-4)", dash: "8 3 2 3" },
];

/** CMP-08: the share of each position over the snapshots. The largest positions get a line
 * of their own, all others together one grey line. Needs two snapshots to draw a course. */
export function AllocationCourse({ snapshots }: { snapshots: Listed[] }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<number | null>(null);
  if (snapshots.length < 2) {
    return <p className="text-sm text-muted-foreground">{t("portfolios.course.hint")}</p>;
  }
  const ordered = [...snapshots].sort(
    (a, b) => Date.parse(a.taken_at) - Date.parse(b.taken_at) || a.id - b.id,
  );
  const share = (s: Listed, ticker: string) =>
    Number(s.allocations.find((a) => a.ticker === ticker)?.allocation_pct ?? 0);
  const tickers = [...new Set(ordered.flatMap((s) => s.allocations.map((a) => a.ticker)))];
  const peak = (ticker: string) => Math.max(...ordered.map((s) => share(s, ticker)));
  tickers.sort((a, b) => peak(b) - peak(a) || a.localeCompare(b));
  const named = tickers.slice(0, STYLES.length);
  const rest = tickers.slice(STYLES.length);
  const series: Series[] = named.map((ticker, i) => ({
    key: ticker,
    label: ticker,
    ...STYLES[i]!,
    values: ordered.map((s) => share(s, ticker)),
  }));
  if (rest.length > 0) {
    series.push({
      key: OTHER,
      label: t("portfolios.course.other"),
      color: "var(--muted-foreground)",
      dash: "1 3",
      values: ordered.map((s) => rest.reduce((sum, ticker) => sum + share(s, ticker), 0)),
    });
  }

  const times = ordered.map((s) => Date.parse(s.taken_at));
  const t0 = times[0]!;
  const span = times[times.length - 1]! - t0 || 1;
  const top =
    Math.min(100, Math.ceil(Math.max(...series.flatMap((s) => s.values)) / 10) * 10) || 10;
  const x = (i: number) => PAD.left + ((times[i]! - t0) / span) * (W - PAD.left - PAD.right);
  const y = (pct: number) => PAD.top + ((top - pct) / top) * (H - PAD.top - PAD.bottom);
  const ticks = [0, top / 2, top];
  const edge = (i: number) => (i === 0 ? 0 : i === ordered.length - 1 ? 1 : 0.5);

  return (
    <figure className="grid gap-1" aria-label={t("portfolios.course.label")}>
      <figcaption className="text-sm text-muted-foreground">
        {t("portfolios.course.caption")}
      </figcaption>
      <div className="relative max-w-2xl">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="presentation">
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--border)"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 6}
                y={y(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-muted-foreground text-[11px]"
              >
                {tick} %
              </text>
            </g>
          ))}
          {[0, ordered.length - 1].map((i) => (
            <text
              key={i}
              x={x(i)}
              y={H - 6}
              textAnchor={i === 0 ? "start" : "end"}
              className="fill-muted-foreground text-[11px]"
            >
              {formatDate(ordered[i]!.taken_at)}
            </text>
          ))}
          {series.map((s) => (
            <path
              key={s.key}
              d={s.values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dash}
              strokeLinejoin="round"
            />
          ))}
          {active !== null && (
            <line
              x1={x(active)}
              x2={x(active)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke="var(--muted-foreground)"
              strokeWidth={1}
            />
          )}
          {series.map((s) =>
            s.values.map((v, i) => (
              <circle
                key={`${s.key}${i}`}
                cx={x(i)}
                cy={y(v)}
                r={active === i ? 4 : 3}
                fill={s.color}
                stroke="var(--background)"
                strokeWidth={1.5}
                pointerEvents="none"
              />
            )),
          )}
          {ordered.map((snapshot, i) => (
            <circle
              key={snapshot.id}
              cx={x(i)}
              cy={H - PAD.bottom}
              r={12}
              fill="transparent"
              tabIndex={0}
              role="img"
              aria-label={`${formatDate(snapshot.taken_at)}: ${series
                .filter((s) => s.values[i]! > 0)
                .map((s) => `${s.label} ${formatPct(s.values[i]!)}`)
                .join(", ")}`}
              className="cursor-default outline-none"
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            />
          ))}
        </svg>
        {active !== null && (
          <div
            role="tooltip"
            className="pointer-events-none absolute top-0 grid gap-0.5 rounded-md border bg-card px-2 py-1 text-xs shadow-md"
            style={{
              left: `${(x(active) / W) * 100}%`,
              transform: `translateX(-${edge(active) * 100}%)`,
            }}
          >
            <span className="font-medium">{formatDate(ordered[active]!.taken_at)}</span>
            {series.map((s) => (
              <span key={s.key}>
                <span
                  className="mr-1 inline-block h-0.5 w-3 align-middle"
                  style={{ background: s.color }}
                  aria-hidden
                />
                {s.label} {formatPct(s.values[active]!)}
              </span>
            ))}
          </div>
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((s) => (
          <li key={s.key} className="flex items-center gap-1">
            <svg width="20" height="6" aria-hidden>
              <line
                x1="0"
                x2="20"
                y1="3"
                y2="3"
                stroke={s.color}
                strokeWidth={2}
                strokeDasharray={s.dash}
              />
            </svg>
            {s.label}
          </li>
        ))}
      </ul>
    </figure>
  );
}
