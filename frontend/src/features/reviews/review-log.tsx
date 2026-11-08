import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { formatScore } from "@/components/stars";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/format";

import { useReview, useReviewLog, type Review, type ReviewLogEntry } from "./api";
import { FullReview, aspectName, reviewerLabel } from "./review";
import { ScoreCourse } from "./score-course";
import { SemaphoreBadge } from "./semaphore";

/** REV-23, THS-08: every saved review of the policy, newest first, with the course of the
 * score; any two of them are compared side by side. */
export function ReviewLog({ policyId }: { policyId: number }) {
  const { t } = useTranslation();
  const log = useReviewLog(policyId);
  const [picked, setPicked] = useState<number[] | null>(null);
  if (log.error) return <FormError error={log.error} />;
  if (!log.data) return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  if (log.data.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("reviews.log.empty")}</p>;
  }
  // By default the newest and the one before it
  const chosen = picked ?? log.data.slice(0, 2).map((e) => e.id);
  const toggle = (id: number) =>
    setPicked(() => {
      if (chosen.includes(id)) return chosen.filter((c) => c !== id);
      return [...chosen, id].slice(-2);
    });
  const [newer, older] = log.data.filter((e) => chosen.includes(e.id));
  return (
    <div className="grid gap-4">
      <ScoreCourse
        points={[...log.data]
          .reverse()
          .filter((e) => e.total !== null)
          .map((e) => ({
            label: e.version_label,
            date: e.saved_at,
            score: e.total!,
            version: e.scoring_version,
          }))}
      />
      <section className="grid gap-2" aria-label={t("reviews.log.title")}>
        <h2 className="font-semibold">{t("reviews.log.title")}</h2>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("reviews.log.compare")}</TableHead>
                <TableHead>{t("reviews.log.date")}</TableHead>
                <TableHead>{t("reviews.log.version")}</TableHead>
                <TableHead>{t("reviews.log.reviewer")}</TableHead>
                <TableHead>{t("reviews.log.score")}</TableHead>
                <TableHead>{t("reviews.log.semaphore")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {log.data.map((e) => (
                <TableRow key={e.id} data-state={chosen.includes(e.id) ? "selected" : undefined}>
                  <TableCell>
                    <input
                      type="checkbox"
                      checked={chosen.includes(e.id)}
                      onChange={() => toggle(e.id)}
                      aria-label={t("reviews.log.pick", {
                        date: formatDate(e.saved_at),
                        version: e.version_label,
                      })}
                    />
                  </TableCell>
                  <TableCell>{formatDate(e.saved_at)}</TableCell>
                  <TableCell>
                    {e.version_label} ·{" "}
                    {e.at_activation ? t("reviews.log.atActivation") : t("reviews.log.again")}
                  </TableCell>
                  <TableCell>{reviewerLabel(e)}</TableCell>
                  <TableCell className="font-medium tabular-nums">
                    {e.total !== null ? formatScore(e.total) : "–"}
                  </TableCell>
                  <TableCell>
                    <SemaphoreBadge semaphore={e.semaphore} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
      {newer && older && <Comparison older={older} newer={newer} />}
    </div>
  );
}

/** REV-23: two reviews side by side: semaphore, scores and every aspect with its
 * difference; the reasoning of both is a click away (REV-24). */
function Comparison({ older, newer }: { older: ReviewLogEntry; newer: ReviewLogEntry }) {
  const { t } = useTranslation();
  const a = useReview(older.id);
  const b = useReview(newer.id);
  const title = t("reviews.log.comparison", {
    from: formatDate(older.saved_at),
    to: formatDate(newer.saved_at),
  });
  if (!a.data || !b.data) return null;
  const codes = [...new Set([...a.data.aspects, ...b.data.aspects].map((x) => x.code))].sort(
    (x, y) => (x[0] === y[0] ? x.localeCompare(y) : x[0] === "T" ? -1 : 1),
  );
  const score = (review: Review, code: string) =>
    review.aspects.find((x) => x.code === code)?.score ?? null;
  const name = (code: string) => {
    const aspect = (b.data!.aspects.find((x) => x.code === code) ??
      a.data!.aspects.find((x) => x.code === code))!;
    return `${code} ${aspectName(aspect, b.data!.scoring_version)}`;
  };
  return (
    <section className="grid gap-2" aria-label={title}>
      <h2 className="font-semibold">{title}</h2>
      {a.data.scoring_version !== b.data.scoring_version && (
        <p className="text-sm text-muted-foreground">{t("reviews.log.versionsDiffer")}</p>
      )}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("reviews.log.aspect")}</TableHead>
              <TableHead>{formatDate(older.saved_at)}</TableHead>
              <TableHead>{formatDate(newer.saved_at)}</TableHead>
              <TableHead>{t("reviews.log.change")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>{t("reviews.log.semaphore")}</TableCell>
              <TableCell>
                <SemaphoreBadge semaphore={a.data.semaphore} />
              </TableCell>
              <TableCell>
                <SemaphoreBadge semaphore={b.data.semaphore} />
              </TableCell>
              <TableCell>–</TableCell>
            </TableRow>
            <ScoreRow label={t("reviews.log.score")} a={a.data.total} b={b.data.total} strong />
            <ScoreRow
              label={t("reviews.score.thesisGroup")}
              a={a.data.thesis_score}
              b={b.data.thesis_score}
            />
            <ScoreRow
              label={t("reviews.score.structureGroup")}
              a={a.data.structure_score}
              b={b.data.structure_score}
            />
            {codes.map((code) => (
              <ScoreRow
                key={code}
                label={name(code)}
                a={score(a.data!, code)}
                b={score(b.data!, code)}
              />
            ))}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <span>
          {formatDate(older.saved_at)}: <FullReview review={a.data} />
        </span>
        <span>
          {formatDate(newer.saved_at)}: <FullReview review={b.data} />
        </span>
      </div>
    </section>
  );
}

function ScoreRow({
  label,
  a,
  b,
  strong,
}: {
  label: string;
  a: number | null;
  b: number | null;
  strong?: boolean;
}) {
  const diff = a !== null && b !== null ? b - a : null;
  const weight = strong ? "font-semibold" : undefined;
  return (
    <TableRow>
      <TableCell className={weight}>{label}</TableCell>
      <TableCell className={`tabular-nums ${weight ?? ""}`}>
        {a !== null ? formatScore(a) : "–"}
      </TableCell>
      <TableCell className={`tabular-nums ${weight ?? ""}`}>
        {b !== null ? formatScore(b) : "–"}
      </TableCell>
      <TableCell
        className={
          diff === null || diff === 0
            ? "tabular-nums"
            : diff > 0
              ? "tabular-nums text-green-700 dark:text-green-400"
              : "tabular-nums text-red-700 dark:text-red-400"
        }
      >
        {diff === null
          ? "–"
          : diff === 0
            ? "0"
            : `${diff > 0 ? "+" : "−"}${formatScore(Math.abs(diff))}`}
      </TableCell>
    </TableRow>
  );
}
