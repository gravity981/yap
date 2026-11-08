import i18n from "i18next";
import { useTranslation } from "react-i18next";

import { NotAdvice } from "@/components/disclaimer";
import { Markdown } from "@/components/markdown";
import { Stars, formatScore } from "@/components/stars";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { currentLanguage } from "@/i18n";
import { formatDate, formatDateTime } from "@/lib/format";

import { isRunning, useReview, type Review, type ReviewBrief } from "./api";
import { SemaphoreBadge, semaphoreLabel, toSemaphore } from "./semaphore";
import { Suggestions, type SuggestionActions } from "./suggestions";

const ASPECT_CODES = ["T1", "T2", "T3", "T4", "T5", "T6", "P1", "P2", "P3", "P4", "P5", "P6"];

const V1_CODES = ["T1", "T2", "T3", "T4", "T5", "T6"];

/** The API names the aspects in English, by the review's scoring version (REV-06); other
 * languages translate them by version and code. */
function aspectName(aspect: { code: string; name: string }, version: string) {
  if (currentLanguage() === "en" || !ASPECT_CODES.includes(aspect.code)) return aspect.name;
  if (version === "1" && V1_CODES.includes(aspect.code)) {
    return i18n.t(`reviews.aspectsV1.${aspect.code as "T1"}`);
  }
  return i18n.t(`reviews.aspects.${aspect.code as "T1"}`);
}

/** "Review", or for a review from before stage 2 which part it judged. */
export function reviewTitle(kind: string | undefined) {
  if (kind === "thesis") return i18n.t("reviews.section.thesis");
  if (kind === "policy") return i18n.t("reviews.section.policy");
  return i18n.t("reviews.section.title");
}

/** A review of a version, read-only: its progress (REV-08) and result. Reviews are
 * started in the draft editor (REV-01, features/reviews/pane.tsx). */
export function ReviewSection({ brief }: { brief: ReviewBrief | null }) {
  const { t } = useTranslation();
  const review = useReview(brief?.id);
  const title = reviewTitle(brief?.kind);
  return (
    <section className="grid gap-3" aria-label={title}>
      <h2 className="text-lg font-semibold">{title}</h2>
      {!brief ? (
        <p className="text-sm text-muted-foreground">{t("reviews.section.notReviewed")}</p>
      ) : !review.data ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : (
        <ReviewResult review={review.data} />
      )}
    </section>
  );
}

export function ReviewResult({
  review,
  actions,
  suggestions = true,
}: {
  review: Review;
  actions?: SuggestionActions;
  suggestions?: boolean;
}) {
  const { t } = useTranslation();

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
          {review.outdated && <Badge variant="warning">{t("reviews.result.outdated")}</Badge>}
          <span className="text-muted-foreground">
            {review.method === "manual" ? (
              reviewerLabel(review)
            ) : (
              <>
                {review.ai_reviewer_name && `${review.ai_reviewer_name}: `}
                {review.provider} {review.model}
              </>
            )}{" "}
            · {t("reviews.result.scoring", { version: review.scoring_version })}
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

        <Total review={review} />
        <Verdict review={review} />
        <Aspects review={review} />
        <LegacyModification review={review} />
        <Sources review={review} />
        {suggestions && <Suggestions review={review} actions={actions} />}

        <NotAdvice short={t("reviews.result.notAdvice")} />
      </CardContent>
    </Card>
  );
}

/** REV-02: the review in short, as in the review pane of the draft editor: whether it
 * matches the draft, who made it, the score, the semaphore, the thesis and
 * target-structure scores with their aspects, and the suggestions. The reasoning is in
 * the full review (REV-24). */
export function ReviewShort({ review, actions }: { review: Review; actions?: SuggestionActions }) {
  const { t } = useTranslation();
  if (isRunning(review.state) || review.state === "failed") return <ReviewResult review={review} />;
  const days =
    review.news_from && review.news_to
      ? Math.round((Date.parse(review.news_to) - Date.parse(review.news_from)) / 86_400_000)
      : null;
  const thesis = review.aspects.filter((a) => a.code.startsWith("T"));
  const structure = review.aspects.filter((a) => a.code.startsWith("P"));
  return (
    <div className="grid gap-4">
      <div className="grid gap-1">
        {!review.confirmed &&
          (review.outdated ? (
            <Badge variant="warning" className="justify-self-start">
              {t("reviews.result.noLongerMatches")}
            </Badge>
          ) : (
            <Badge variant="success" className="justify-self-start">
              {t("reviews.result.matches")}
            </Badge>
          ))}
        <p className="text-sm text-muted-foreground">
          {reviewerLabel(review)}
          {review.completed_at && ` · ${formatDateTime(review.completed_at)}`}
          {days !== null && ` · ${t("reviews.result.newsDays", { count: days })}`}
        </p>
      </div>
      <Total review={review} />
      {review.kind === "full" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <ShortGroup
            title={t("reviews.score.thesis", { score: formatScore(review.thesis_score ?? 0) })}
            review={review}
            aspects={thesis}
          />
          {structure.length > 0 ? (
            <ShortGroup
              title={t("reviews.score.structure", {
                score: formatScore(review.structure_score ?? 0),
              })}
              review={review}
              aspects={structure}
            />
          ) : (
            <p className="text-sm text-muted-foreground">{t("reviews.result.noStructure")}</p>
          )}
        </div>
      )}
      <FullReview review={review} />
      <Suggestions review={review} actions={actions} />
    </div>
  );
}

function ShortGroup({
  title,
  review,
  aspects,
}: {
  title: string;
  review: Review;
  aspects: Review["aspects"];
}) {
  return (
    <div className="grid content-start gap-1 text-sm">
      <p className="font-medium">{title}</p>
      <ul className="grid gap-0.5">
        {aspects.map((a) => (
          <li
            key={a.code}
            className={
              a.score < 6.5
                ? "flex justify-between gap-2 text-amber-800 dark:text-amber-300"
                : "flex justify-between gap-2"
            }
          >
            <span className="truncate">
              {a.code} {aspectName(a, review.scoring_version)}
            </span>
            <span className="font-medium tabular-nums">{formatScore(a.score)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** REV-24: the whole review in a dialog: reviewer, date, news period and scoring version,
 * score and semaphore with the reason, every aspect with its reasoning, the sources. */
export function FullReview({ review }: { review: Review }) {
  const { t } = useTranslation();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="link" className="h-auto justify-self-start p-0">
          {t("reviews.full.open")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogTitle>{t("reviews.full.title")}</DialogTitle>
        <DialogDescription className="sr-only">{t("reviews.full.description")}</DialogDescription>
        <ReviewResult review={review} suggestions={false} />
        <p className="text-sm text-muted-foreground">{t("reviews.full.suggestionsInPane")}</p>
      </DialogContent>
    </Dialog>
  );
}

/** REV-02: the score as stars, the semaphore, and the thesis and target-structure scores
 * of a review of the whole policy. */
function Total({ review }: { review: Review }) {
  const { t } = useTranslation();
  if (review.total === null) return null;
  const parts = review.kind === "full";
  return (
    <div className="grid gap-1">
      <div className="flex flex-wrap items-center gap-3" aria-label={t("reviews.score.totalLabel")}>
        <Stars score={review.total} label={t("reviews.score.totalLabel")} />
        <span className="text-lg font-semibold tabular-nums">
          {t("reviews.score.outOf", { score: formatScore(review.total) })}
        </span>
        {review.semaphore && <SemaphoreBadge semaphore={review.semaphore} />}
      </div>
      {parts && (
        <p className="text-sm text-muted-foreground">
          {review.thesis_score !== null &&
            t("reviews.score.thesis", { score: formatScore(review.thesis_score) })}
          {review.structure_score !== null &&
            ` · ${t("reviews.score.structure", { score: formatScore(review.structure_score) })}`}
        </p>
      )}
    </div>
  );
}

/** REV-03: the reason for the verdict, since scoring version 3. */
function Verdict({ review }: { review: Review }) {
  const { t } = useTranslation();
  if (!review.verdict_reason) return null;
  return (
    <p className="text-sm">
      <span className="font-medium">{t("reviews.score.verdict")}</span> {review.verdict_reason}
    </p>
  );
}

/** Changes the investor made before reviews became read-only (REV-10 dropped). */
function LegacyModification({ review }: { review: Review }) {
  const { t } = useTranslation();
  const legacy = review.legacy_modification;
  if (!legacy) return null;
  const names = Object.fromEntries(
    review.aspects.map((a) => [a.code, aspectName(a, review.scoring_version)]),
  );
  return (
    <div className="grid gap-1 rounded-md border border-dashed p-3 text-sm">
      <p className="font-medium">{t("reviews.legacy.title")}</p>
      <ul className="grid gap-0.5">
        {legacy.verdict && (
          <li>
            {t("reviews.legacy.verdict", { verdict: semaphoreLabel(toSemaphore(legacy.verdict)) })}
          </li>
        )}
        {Object.entries(legacy.scores).map(([code, score]) => (
          <li key={code}>
            {t("reviews.legacy.score", {
              name: `${code} ${names[code] ?? ""}`.trim(),
              score: formatScore(score),
            })}
          </li>
        ))}
        {legacy.note && <li>{t("reviews.legacy.note", { note: legacy.note })}</li>}
      </ul>
    </div>
  );
}

/** REV-02, REV-24: every aspect with its score and reasoning, grouped by thesis and target
 * structure. */
function Aspects({ review }: { review: Review }) {
  const { t } = useTranslation();
  const thesis = review.aspects.filter((a) => a.code.startsWith("T"));
  const structure = review.aspects.filter((a) => a.code.startsWith("P"));
  if (review.kind !== "full") return <AspectList review={review} aspects={review.aspects} />;
  return (
    <div className="grid gap-3">
      <h3 className="font-medium">{t("reviews.score.thesisGroup")}</h3>
      <AspectList review={review} aspects={thesis} />
      {structure.length > 0 && (
        <>
          <h3 className="font-medium">{t("reviews.score.structureGroup")}</h3>
          <AspectList review={review} aspects={structure} />
        </>
      )}
    </div>
  );
}

function AspectList({ review, aspects }: { review: Review; aspects: Review["aspects"] }) {
  return (
    <ol className="grid gap-3">
      {aspects.map((a) => (
        <li key={a.code} className="grid gap-1 rounded-md border p-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">
              {a.code} {aspectName(a, review.scoring_version)}
            </span>
            <span className="flex flex-wrap items-center gap-2 text-sm">
              <Stars score={a.score} label={aspectName(a, review.scoring_version)} />
              <span className="tabular-nums">{formatScore(a.score)}</span>
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

const STATES = ["queued", "running", "done", "failed"] as const;

/** queued, running, done or failed in the current language; unknown values as they are. */
function reviewState(state: string): string {
  return (STATES as readonly string[]).includes(state)
    ? i18n.t(`reviews.states.${state as (typeof STATES)[number]}`)
    : state;
}

/** REV-17: who made a review, e.g. "Standard (claude-x)" or "manual review"; manual
 * reviews from before stage 2 name the model the investor gave. */
export function reviewerLabel(review: {
  method: string;
  model: string | null;
  ai_reviewer_name?: string | null;
}): string {
  if (review.method === "manual") {
    return review.model
      ? i18n.t("reviews.result.manualWith", { model: review.model })
      : i18n.t("reviews.result.manual");
  }
  const model = review.model ?? "";
  return review.ai_reviewer_name ? `${review.ai_reviewer_name} (${model})` : model;
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
      {brief.semaphore && <SemaphoreBadge semaphore={brief.semaphore} />}
      <span className="text-muted-foreground">{reviewerLabel(brief)}</span>
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
  const review = useReview(reviewId);
  if (!review.data) return null;
  const r = review.data;
  return (
    <div className="grid gap-2 text-sm">
      <p className="text-muted-foreground">{reviewerLabel(r)}</p>
      <Total review={r} />
      <FullReview review={r} />
      <ul className="grid gap-1">
        {r.aspects.map((a) => (
          <li key={a.code} className="flex flex-wrap items-center gap-2">
            <span className="w-56">
              {a.code} {aspectName(a, r.scoring_version)}
            </span>
            <Stars score={a.score} label={aspectName(a, r.scoring_version)} />
            <span className="tabular-nums">{formatScore(a.score)}</span>
          </li>
        ))}
      </ul>
      <LegacyModification review={r} />
    </div>
  );
}
