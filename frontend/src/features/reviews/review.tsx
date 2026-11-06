import { Link } from "@tanstack/react-router";
import i18n from "i18next";
import { useState, type FormEvent } from "react";
import { Trans, useTranslation } from "react-i18next";

import { translateMessage } from "@/api/client";
import { useMe } from "@/auth/auth";
import { NotAdvice } from "@/components/disclaimer";
import { Field, FormError, fieldError } from "@/components/form";
import { Markdown } from "@/components/markdown";
import { Stars, formatScore } from "@/components/stars";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { statusLabel } from "@/features/theses/status";
import { currentLanguage } from "@/i18n";
import { formatDate, formatDateTime } from "@/lib/format";

import {
  isRunning,
  useModifyReview,
  useReview,
  useReviewerOptions,
  useStartReview,
  useUsage,
  type Review,
  type ReviewBrief,
  type ReviewKind,
} from "./api";

const VERDICTS = ["intact", "needs_adaptation", "broken"] as const;
const SCORES = Array.from({ length: 21 }, (_, i) => i / 2);
const SUGGESTION_KINDS = ["thesis_text", "thesis_status", "policy_position"] as const;
const ASPECT_CODES = ["T1", "T2", "T3", "T4", "T5", "T6", "P1", "P2", "P3", "P4", "P5", "P6"];

/** REV-03: the verdict uses the thesis status labels. */
export function verdictLabel(verdict: string) {
  return statusLabel(verdict);
}

function suggestionLabel(kind: string) {
  return (SUGGESTION_KINDS as readonly string[]).includes(kind)
    ? i18n.t(`reviews.suggestions.${kind as (typeof SUGGESTION_KINDS)[number]}`)
    : kind;
}

/** The API names the aspects in English; other languages translate them by code. */
function aspectName(aspect: { code: string; name: string }) {
  if (currentLanguage() === "en" || !ASPECT_CODES.includes(aspect.code)) return aspect.name;
  return i18n.t(`reviews.aspects.${aspect.code as "T1"}`);
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const variant =
    verdict === "broken" ? "destructive" : verdict === "needs_adaptation" ? "warning" : "success";
  return <Badge variant={variant}>{verdictLabel(verdict)}</Badge>;
}

/** The review of one revision or version: start it on an own draft (REV-01), follow its
 * progress (REV-08), show and modify the result (REV-10); read-only once confirmed. */
export function ReviewSection({
  kind,
  ownerId,
  brief,
  canStart,
}: {
  kind: ReviewKind;
  ownerId: number; // thesis or policy ID
  brief: ReviewBrief | null;
  canStart: boolean; // an own draft
}) {
  const { t } = useTranslation();
  const review = useReview(brief?.id);
  const title = kind === "thesis" ? t("reviews.section.thesis") : t("reviews.section.policy");
  return (
    <section className="grid gap-3" aria-label={title}>
      <h2 className="text-lg font-semibold">{title}</h2>
      {!brief ? (
        canStart ? (
          <StartReview kind={kind} ownerId={ownerId} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("reviews.section.notReviewed")}</p>
        )
      ) : !review.data ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : (
        <ReviewResult kind={kind} ownerId={ownerId} review={review.data} editable={canStart} />
      )}
    </section>
  );
}

function StartReview({
  kind,
  ownerId,
  again,
}: {
  kind: ReviewKind;
  ownerId: number;
  again?: boolean;
}) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const options = useReviewerOptions();
  // USR-08: preselected with the default from the settings, if it is still available
  const [picked, setPicked] = useState<number | null>(null);
  const fallback =
    options.data?.find((o) => o.id === me?.ai_reviewer_id)?.id ?? options.data?.[0]?.id ?? null;
  const reviewerId = picked ?? fallback;
  const usage = useUsage(reviewerId, reviewerId !== null);
  const start = useStartReview(kind, ownerId);
  const [days, setDays] = useState("90");
  const unavailable =
    options.data?.length === 0
      ? t("reviews.start.noReviewers")
      : usage.data?.unavailable_reason &&
        // NFR-10: the reason in the UI language, by its code
        translateMessage(
          usage.data.unavailable_code,
          usage.data.unavailable_params,
          usage.data.unavailable_reason,
        );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (reviewerId === null) return;
    start.mutate({ reviewerId, newsDays: kind === "thesis" ? Number(days) : undefined });
  };
  return (
    <form className="grid gap-3" onSubmit={submit} aria-label={t("reviews.start.form")}>
      {!again && (
        <p className="text-sm text-muted-foreground">
          {kind === "thesis" ? t("reviews.start.introThesis") : t("reviews.start.introPolicy")}
        </p>
      )}
      {/* NFR-01, NFR-15: what leaves the server, before anything is sent */}
      <p className="text-sm text-muted-foreground">
        {kind === "thesis" ? t("reviews.start.dataThesis") : t("reviews.start.dataPolicy")}
        {t("reviews.start.dataNothingElse")}
      </p>
      <div className="flex flex-wrap items-end gap-3">
        {options.data && options.data.length > 0 && (
          <Field id={`${kind}-ai-reviewer`} label={t("reviews.start.reviewer")}>
            <NativeSelect
              id={`${kind}-ai-reviewer`}
              className="w-auto"
              value={reviewerId ?? ""}
              onChange={(e) => setPicked(Number(e.target.value))}
            >
              {options.data.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                  {o.id === me?.ai_reviewer_id ? t("reviews.start.default") : ""}
                </option>
              ))}
            </NativeSelect>
          </Field>
        )}
        {kind === "thesis" && (
          <Field
            id="news-days"
            label={t("reviews.start.newsDays")}
            error={fieldError(start.error, "news_days")}
          >
            <Input
              id="news-days"
              type="number"
              min={1}
              max={365}
              className="w-28"
              value={days}
              onChange={(e) => setDays(e.target.value)}
              required
            />
          </Field>
        )}
        <Button
          type="submit"
          disabled={start.isPending || !!unavailable || !usage.data || reviewerId === null}
        >
          {again ? t("reviews.start.again") : t("reviews.start.button")}
        </Button>
        {usage.data?.ai_reviewer_name && (
          <span className="pb-2 text-sm text-muted-foreground">
            {t("reviews.start.usage", {
              used: usage.data.used,
              limit: usage.data.limit,
              name: usage.data.ai_reviewer_name,
            })}
          </span>
        )}
      </div>
      {options.data?.find((o) => o.id === reviewerId)?.description && (
        <p className="text-sm text-muted-foreground">
          {options.data.find((o) => o.id === reviewerId)?.description}
        </p>
      )}
      {unavailable && <Alert variant="warning">{unavailable}</Alert>}
      <p className="text-xs text-muted-foreground">
        <Trans
          i18nKey="reviews.start.defaultIn"
          components={{ link: <Link to="/settings" className="underline" /> }}
        />
      </p>
      <FormError error={start.error ?? usage.error} fields={["news_days"]} />
    </form>
  );
}

function ReviewResult({
  kind,
  ownerId,
  review,
  editable,
}: {
  kind: ReviewKind;
  ownerId: number;
  review: Review;
  editable: boolean;
}) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const open = editable && !review.confirmed;

  if (isRunning(review.state)) {
    return (
      <Alert role="status">
        {t("reviews.result.running", { started: formatDateTime(review.started_at) })}
      </Alert>
    );
  }
  if (review.state === "failed") {
    return (
      <div className="grid gap-3">
        <Alert variant="destructive">{t("reviews.result.failed", { error: review.error })}</Alert>
        {open && <StartReview kind={kind} ownerId={ownerId} again />}
      </div>
    );
  }
  return (
    <Card>
      <CardContent className="grid gap-4 pt-5">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {review.confirmed ? (
            <Badge variant="secondary">{t("reviews.result.confirmed")}</Badge>
          ) : (
            <Badge variant="outline">{t("reviews.result.notConfirmed")}</Badge>
          )}
          {review.modified && <Badge variant="warning">{t("reviews.result.modified")}</Badge>}
          {review.outdated && <Badge variant="warning">{t("reviews.result.outdated")}</Badge>}
          <span className="text-muted-foreground">
            {review.ai_reviewer_name && `${review.ai_reviewer_name}: `}
            {review.provider} {review.model} ·{" "}
            {t("reviews.result.scoring", { version: review.scoring_version })}
            {review.news_from && review.news_to && (
              <>
                {" · "}
                {t("reviews.result.news", {
                  from: formatDate(review.news_from),
                  to: formatDate(review.news_to),
                })}
              </>
            )}
          </span>
        </div>

        <Totals review={review} />

        {editing ? (
          <ModifyForm review={review} onDone={() => setEditing(false)} />
        ) : (
          <>
            <Aspects review={review} />
            {review.modification_note && (
              <p className="text-sm">
                <span className="font-medium">{t("reviews.result.whyChanged")}</span>{" "}
                {review.modification_note}
              </p>
            )}
            <Sources review={review} />
            <Suggestions review={review} />
          </>
        )}

        <NotAdvice short={t("reviews.result.notAdvice")} />
        {open && !editing && (
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" onClick={() => setEditing(true)}>
              {t("reviews.result.change")}
            </Button>
          </div>
        )}
        {open && !editing && (
          <div className="border-t pt-4">
            <StartReview kind={kind} ownerId={ownerId} again />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** REV-10: the AI's stars and the investor's side by side. */
function Totals({ review }: { review: Review }) {
  const { t } = useTranslation();
  if (review.total === null || review.ai_total === null) return null;
  return (
    <div className="grid gap-2" aria-label={t("reviews.score.totalLabel")}>
      <ScoreLine
        label={t("reviews.score.ai")}
        score={review.ai_total}
        verdict={review.ai_verdict}
        strong={!review.modified}
      />
      {review.modified && (
        <ScoreLine
          label={t("reviews.score.yours")}
          score={review.total}
          verdict={review.verdict}
          strong
        />
      )}
    </div>
  );
}

function ScoreLine({
  label,
  score,
  verdict,
  strong,
}: {
  label: string;
  score: number;
  verdict: string | null;
  strong: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="w-12 text-sm text-muted-foreground">{label}</span>
      <Stars score={score} label={t("reviews.score.total", { who: label })} />
      <span className={strong ? "text-lg font-semibold tabular-nums" : "tabular-nums"}>
        {t("reviews.score.outOf", { score: formatScore(score) })}
      </span>
      {verdict && <VerdictBadge verdict={verdict} />}
    </div>
  );
}

function Aspects({ review }: { review: Review }) {
  const { t } = useTranslation();
  return (
    <ol className="grid gap-3">
      {review.aspects.map((a) => (
        <li key={a.code} className="grid gap-1 rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">
              {a.code} {aspectName(a)}
            </span>
            <span className="flex flex-wrap items-center gap-2 text-sm">
              <Stars
                score={a.ai_score}
                label={t("reviews.score.aspectAi", { name: aspectName(a) })}
              />
              <span className="tabular-nums">{formatScore(a.ai_score)}</span>
              {a.modified && (
                <>
                  <span className="text-muted-foreground">{t("reviews.score.yoursShort")}</span>
                  <Stars
                    score={a.score}
                    label={t("reviews.score.aspectYours", { name: aspectName(a) })}
                  />
                  <span className="tabular-nums font-medium">{formatScore(a.score)}</span>
                </>
              )}
            </span>
          </div>
          <div className="text-sm">
            <Markdown source={a.reasoning_md} />
          </div>
        </li>
      ))}
    </ol>
  );
}

function Sources({ review }: { review: Review }) {
  const { t } = useTranslation();
  if (review.sources.length === 0) return null;
  return (
    <div className="grid gap-1">
      <h3 className="font-medium">{t("reviews.sources")}</h3>
      <ol className="list-decimal pl-6 text-sm">
        {review.sources.map((s, i) => (
          <li key={i}>
            <a href={s.url} target="_blank" rel="noreferrer noopener" className="underline">
              {s.title}
            </a>
            {s.published_on && <span className="text-muted-foreground"> ({s.published_on})</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** REV-07: suggestions are never applied automatically. */
function Suggestions({ review }: { review: Review }) {
  const { t } = useTranslation();
  if (review.suggestions.length === 0) return null;
  return (
    <div className="grid gap-2">
      <h3 className="font-medium">{t("reviews.suggestions.title")}</h3>
      <p className="text-sm text-muted-foreground">{t("reviews.suggestions.note")}</p>
      <ul className="grid gap-2">
        {review.suggestions.map((s, i) => (
          <li key={i} className="rounded-md border p-3 text-sm">
            <Badge variant="outline">{suggestionLabel(s.kind)}</Badge>
            <div className="mt-2">
              <Markdown source={s.content_md} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** REV-10: the investor's values next to the AI's; "AI" keeps the AI's value. */
function ModifyForm({ review, onDone }: { review: Review; onDone: () => void }) {
  const { t } = useTranslation();
  const modify = useModifyReview(review.id);
  const [scores, setScores] = useState<Record<string, string>>(() =>
    Object.fromEntries(review.aspects.map((a) => [a.code, a.modified ? String(a.score) : ""])),
  );
  const [verdict, setVerdict] = useState(
    review.verdict !== review.ai_verdict ? (review.verdict ?? "") : "",
  );
  const [note, setNote] = useState(review.modification_note ?? "");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    modify.mutate(
      {
        scores: Object.fromEntries(
          Object.entries(scores).map(([code, value]) => [
            code,
            value === "" ? null : Number(value),
          ]),
        ),
        verdict: verdict || null,
        note: note.trim() || null,
      },
      { onSuccess: onDone },
    );
  };
  return (
    <form className="grid gap-3" onSubmit={submit} aria-label={t("reviews.modify.form")}>
      <p className="text-sm text-muted-foreground">{t("reviews.modify.intro")}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {review.aspects.map((a) => (
          <Field key={a.code} id={`score-${a.code}`} label={`${a.code} ${aspectName(a)}`}>
            <NativeSelect
              id={`score-${a.code}`}
              value={scores[a.code]}
              onChange={(e) => setScores({ ...scores, [a.code]: e.target.value })}
            >
              <option value="">
                {t("reviews.modify.keepAi", { value: formatScore(a.ai_score) })}
              </option>
              {SCORES.map((s) => (
                <option key={s} value={String(s)}>
                  {formatScore(s)}
                </option>
              ))}
            </NativeSelect>
          </Field>
        ))}
        {review.kind === "thesis" && review.ai_verdict && (
          <Field id="verdict" label={t("reviews.modify.verdict")}>
            <NativeSelect id="verdict" value={verdict} onChange={(e) => setVerdict(e.target.value)}>
              <option value="">
                {t("reviews.modify.keepAi", { value: verdictLabel(review.ai_verdict) })}
              </option>
              {VERDICTS.map((v) => (
                <option key={v} value={v}>
                  {verdictLabel(v)}
                </option>
              ))}
            </NativeSelect>
          </Field>
        )}
      </div>
      <Field
        id="modification-note"
        label={t("reviews.modify.note")}
        error={fieldError(modify.error, "note")}
      >
        <Input id="modification-note" value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <FormError error={modify.error} fields={["note"]} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={modify.isPending}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}

const STATES = ["queued", "running", "done", "failed"] as const;

/** queued, running, done or failed in the current language; unknown values as they are. */
function reviewState(state: string): string {
  return (STATES as readonly string[]).includes(state)
    ? i18n.t(`reviews.states.${state as (typeof STATES)[number]}`)
    : state;
}

/** A review in one line, e.g. in a history list (THS-08). */
export function ReviewBriefLine({ brief }: { brief: ReviewBrief | null | undefined }) {
  const { t } = useTranslation();
  if (!brief) return null;
  if (brief.state !== "done" || brief.total === null) {
    return (
      <span className="text-sm text-muted-foreground">
        {t("reviews.brief.state", { state: reviewState(brief.state) })}
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <Stars score={brief.total} label={t("reviews.brief.label")} />
      <span className="tabular-nums">{formatScore(brief.total)}</span>
      {brief.verdict && <VerdictBadge verdict={brief.verdict} />}
      {brief.modified && <Badge variant="warning">{t("reviews.result.modified")}</Badge>}
    </span>
  );
}

/** REV-11: activating without a current review asks for confirmation first. */
export function activationWarning(brief: ReviewBrief | null | undefined): string | null {
  if (!brief || brief.state === "failed") {
    return i18n.t("reviews.activation.noReview");
  }
  if (isRunning(brief.state)) return null; // the server refuses activation meanwhile
  if (brief.outdated) {
    return i18n.t("reviews.activation.outdated");
  }
  return null;
}

/** TL-02: the result of a confirmed review, e.g. in a timeline event. */
export function ReviewDetails({ reviewId }: { reviewId: number }) {
  const { t } = useTranslation();
  const review = useReview(reviewId);
  if (!review.data) return null;
  const r = review.data;
  return (
    <div className="grid gap-2 text-sm">
      <Totals review={r} />
      <ul className="grid gap-1">
        {r.aspects.map((a) => (
          <li key={a.code} className="flex flex-wrap items-center gap-2">
            <span className="w-56">
              {a.code} {aspectName(a)}
            </span>
            <Stars score={a.score} label={aspectName(a)} />
            <span className="tabular-nums">{formatScore(a.score)}</span>
            {a.modified && (
              <span className="text-muted-foreground">
                {t("reviews.score.aiValue", { score: formatScore(a.ai_score) })}
              </span>
            )}
          </li>
        ))}
      </ul>
      {r.modification_note && (
        <p>{t("reviews.details.changedBecause", { note: r.modification_note })}</p>
      )}
    </div>
  );
}
