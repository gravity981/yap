import i18n from "i18next";
import { useTranslation } from "react-i18next";

import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatPct } from "@/lib/format";

import type { Version } from "./api";

/** Shape of a version diff as returned by the API client (pairs arrive as arrays). */
export interface VersionDiffLike {
  positions: { ticker: string; change: string; fields: Record<string, string[]> }[];
  thesis_revision: number[] | null;
}

/** Target structure with absolute bands (POL-02, POL-04). */
export function PositionsTable({ version }: { version: Version }) {
  const { t } = useTranslation();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("policies.positions.position")}</TableHead>
          <TableHead>{t("policies.positions.type")}</TableHead>
          <TableHead className="text-right">{t("policies.positions.target")}</TableHead>
          <TableHead className="text-right">{t("policies.positions.buyBelow")}</TableHead>
          <TableHead className="text-right">{t("policies.positions.sellAbove")}</TableHead>
          <TableHead className="text-right">{t("policies.positions.midband")}</TableHead>
          <TableHead>{t("policies.positions.rationale")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {version.positions.map((p) => (
          <TableRow key={p.ticker}>
            <TableCell>
              <span className="font-medium">{p.ticker}</span>{" "}
              <span className="text-muted-foreground">{p.name}</span>{" "}
              {p.exit && <Badge variant="destructive">{t("policies.positions.exit")}</Badge>}
            </TableCell>
            <TableCell>{assetTypeLabel(p.type)}</TableCell>
            <TableCell className="text-right">{formatPct(p.target_pct)}</TableCell>
            <TableCell
              className="text-right"
              title={t("policies.positions.buyTitle", { pct: p.buy_threshold_pct })}
            >
              {formatPct(p.buy_abs_pct)}
            </TableCell>
            <TableCell
              className="text-right"
              title={t("policies.positions.sellTitle", { pct: p.sell_threshold_pct })}
            >
              {formatPct(p.sell_abs_pct)}
            </TableCell>
            <TableCell className="text-right">{formatPct(p.midband_pct)}</TableCell>
            <TableCell className="max-w-md">
              {p.rationale_md ? (
                <details>
                  <summary className="cursor-pointer text-sm text-muted-foreground">
                    {t("policies.positions.show")}
                  </summary>
                  <Markdown source={p.rationale_md} className="mt-2 text-sm" />
                </details>
              ) : (
                "–"
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

const ASSET_TYPES = ["ETF", "stock", "crypto", "cash_buffer"] as const;
const DIFF_FIELDS = [
  "target_pct",
  "buy_threshold_pct",
  "sell_threshold_pct",
  "exit",
  "rationale_md",
] as const;

/** An asset type in the current language; unknown types as they come. */
export function assetTypeLabel(type: string): string {
  return (ASSET_TYPES as readonly string[]).includes(type)
    ? i18n.t(`domain.assetType.${type as (typeof ASSET_TYPES)[number]}`)
    : type;
}

function fieldLabel(field: string): string {
  return (DIFF_FIELDS as readonly string[]).includes(field)
    ? i18n.t(`policies.diff.field.${field as (typeof DIFF_FIELDS)[number]}`)
    : field;
}

/** POL-09, IMP-07: what changes between two versions. */
export function VersionDiffView({ diff }: { diff: VersionDiffLike }) {
  const { t } = useTranslation();
  const nothing = diff.positions.length === 0 && !diff.thesis_revision;
  if (nothing) return <p className="text-sm text-muted-foreground">{t("policies.diff.none")}</p>;
  return (
    <ul className="grid gap-1 text-sm">
      {diff.positions.map((c) => (
        <li key={c.ticker}>
          <span className="font-medium">{c.ticker}</span>{" "}
          {c.change === "added" && <Badge variant="success">{t("policies.diff.added")}</Badge>}
          {c.change === "removed" && (
            <Badge variant="destructive">{t("policies.diff.removed")}</Badge>
          )}
          {c.change === "changed" &&
            Object.entries(c.fields).map(([field, [before, after]]) => (
              <span key={field} className="mr-2">
                {fieldLabel(field)}:{" "}
                {field === "rationale_md" ? t("policies.diff.changed") : `${before} → ${after}`}
              </span>
            ))}
        </li>
      ))}
      {diff.thesis_revision && (
        <li>
          {t("policies.diff.thesisRevision", {
            from: diff.thesis_revision[0],
            to: diff.thesis_revision[1],
          })}
        </li>
      )}
    </ul>
  );
}
