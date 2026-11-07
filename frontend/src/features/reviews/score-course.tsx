import { useState } from "react";
import { useTranslation } from "react-i18next";

import { formatScore } from "@/components/stars";
import { formatDate } from "@/lib/format";

export interface ScorePoint {
  label: string; // e.g. "Revision 3"
  date: string;
  score: number;
  version: string; // REV-06: the scoring version of the review
}

const W = 480;
const H = 160;
const PAD = { left: 28, right: 16, top: 12, bottom: 24 };

/** THS-08: the total score of the confirmed reviews over the revisions. One series, so
 * no legend; the history list next to it holds the same values as text. Where the scoring
 * version changes, the line breaks and a marker names the new version (REV-06). */
export function ScoreCourse({ points }: { points: ScorePoint[] }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<number | null>(null);
  if (points.length < 2) return null;
  const x = (i: number) => PAD.left + (i * (W - PAD.left - PAD.right)) / (points.length - 1);
  const y = (score: number) => PAD.top + ((10 - score) * (H - PAD.top - PAD.bottom)) / 10;
  const changes = points.flatMap((p, i) =>
    i > 0 && p.version !== points[i - 1]?.version ? [i] : [],
  );
  const line = points
    .map((p, i) => `${i === 0 || changes.includes(i) ? "M" : "L"}${x(i)},${y(p.score)}`)
    .join(" ");
  const shown = active === null ? null : points[active];

  return (
    <figure className="grid gap-1" aria-label={t("reviews.course.label")}>
      <figcaption className="text-sm text-muted-foreground">
        {t("reviews.course.caption")}
        {changes.length > 0 && ` ${t("reviews.course.versionNote")}`}
      </figcaption>
      <div className="relative max-w-xl">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="presentation">
          {[0, 5, 10].map((tick) => (
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
                {tick}
              </text>
            </g>
          ))}
          {points.map((p, i) => (
            <text
              key={p.label}
              x={x(i)}
              y={H - 6}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {/* The axis shows "r3" for "Revision 3" */}
              {t("reviews.course.tick", { no: p.label.match(/\d+$/)?.[0] ?? p.label })}
            </text>
          ))}
          {changes.map((i) => (
            <g key={`v${i}`} data-testid="version-change">
              <line
                x1={(x(i - 1) + x(i)) / 2}
                x2={(x(i - 1) + x(i)) / 2}
                y1={PAD.top}
                y2={H - PAD.bottom}
                stroke="var(--muted-foreground)"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              <text
                x={(x(i - 1) + x(i)) / 2 + 4}
                y={PAD.top + 8}
                className="fill-muted-foreground text-[11px]"
              >
                {t("reviews.course.version", { version: points[i]?.version })}
              </text>
            </g>
          ))}
          <path
            d={line}
            fill="none"
            stroke="var(--series-1)"
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {points.map((p, i) => (
            <g key={p.label}>
              {/* The hit target is bigger than the marker */}
              <circle
                cx={x(i)}
                cy={y(p.score)}
                r={12}
                fill="transparent"
                tabIndex={0}
                role="img"
                aria-label={t("reviews.course.point", {
                  label: p.label,
                  score: formatScore(p.score),
                })}
                className="cursor-default outline-none"
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              />
              <circle
                cx={x(i)}
                cy={y(p.score)}
                r={active === i ? 5 : 4}
                fill="var(--series-1)"
                stroke="var(--background)"
                strokeWidth={2}
                pointerEvents="none"
              />
            </g>
          ))}
        </svg>
        {shown && active !== null && (
          <div
            role="tooltip"
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-md border bg-card px-2 py-1 text-xs shadow-md"
            style={{ left: `${(x(active) / W) * 100}%`, top: `${(y(shown.score) / H) * 100}%` }}
          >
            <span className="font-medium">{shown.label}</span>
            {t("reviews.course.tooltip", { score: formatScore(shown.score) })}
            <span className="text-muted-foreground"> · {formatDate(shown.date)}</span>
          </div>
        )}
      </div>
    </figure>
  );
}
