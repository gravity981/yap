import { Link } from "@tanstack/react-router";
import { useState, type FormEvent, type ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";

import { ApiError, translateMessage } from "@/api/client";
import { useMe } from "@/auth/auth";
import { Field, FormError } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import type { Version } from "@/features/policies/api";

import {
  isRunning,
  useReview,
  useReviewPrompt,
  useReviewerOptions,
  useStartReview,
  useSubmitManualReview,
  useUsage,
  type ReviewBrief,
  type ReviewTarget,
} from "./api";
import { ReviewShort } from "./review";

/** An AI reviewer's ID, or a manual review (REV-18). */
type Method = number | "manual";

/** REV-01: the review of the whole draft in the editor: thesis and target structure. The
 * result stays visible while the investor edits; a new review replaces it (REV-09). `save`
 * stores what is in the editor first, so the review sees the current content. */
export function ReviewPane({
  policyId,
  brief,
  save,
  onDraft,
  target = "draft",
}: {
  policyId: number;
  brief: ReviewBrief | null | undefined;
  save: () => Promise<unknown>;
  /** REV-07: the draft after a suggestion was taken over, dismissed or undone */
  onDraft: (draft: Version | null) => void;
  /** POL-20, REV-26: on the policy page, the active version gets a quick review */
  target?: ReviewTarget;
}) {
  const { t } = useTranslation();
  const review = useReview(brief?.id);
  const running = isRunning(review.data?.state ?? brief?.state);
  // On the policy page the pane is part of the "Quick review" section (POL-20)
  const label = target === "draft" ? t("reviews.section.title") : undefined;
  return (
    <section className="grid content-start gap-4" aria-label={label}>
      {!brief ? (
        target === "draft" && <Alert variant="warning">{t("reviews.pane.noReview")}</Alert>
      ) : review.data ? (
        <ReviewShort
          review={review.data}
          actions={{ save, onDraft, activeVersion: target === "active" }}
        />
      ) : (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      )}
      {!running && (
        <div className={brief ? "border-t pt-4" : undefined}>
          <ReviewForm policyId={policyId} again={!!brief} save={save} target={target} />
        </div>
      )}
    </section>
  );
}

function ReviewForm({
  policyId,
  again,
  save,
  target,
}: {
  policyId: number;
  again: boolean;
  target: ReviewTarget;
  save: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const options = useReviewerOptions();
  const [picked, setPicked] = useState<Method | null>(null);
  // USR-08: the default method, if still available; manual if there is no AI reviewer
  const fallback: Method | null = !options.data
    ? null
    : me?.manual_review_default
      ? "manual"
      : (options.data.find((o) => o.id === me?.ai_reviewer_id)?.id ??
        options.data[0]?.id ??
        "manual");
  const method = picked ?? fallback;
  const [days, setDays] = useState("90");
  const newsDays = Number(days);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field id="review-method" label={t("reviews.pane.method")}>
          <NativeSelect
            id="review-method"
            className="w-auto"
            value={method ?? ""}
            onChange={(e) =>
              setPicked(e.target.value === "manual" ? "manual" : Number(e.target.value))
            }
          >
            {options.data?.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
                {!me?.manual_review_default && o.id === me?.ai_reviewer_id
                  ? t("reviews.start.default")
                  : ""}
              </option>
            ))}
            <option value="manual">
              {t("reviews.pane.manual")}
              {me?.manual_review_default ? t("reviews.start.default") : ""}
            </option>
          </NativeSelect>
        </Field>
        {/* REV-04: the news period of T6 and the verdict */}
        <Field id="review-news-days" label={t("reviews.start.newsDays")}>
          <Input
            id="review-news-days"
            type="number"
            min={1}
            max={365}
            className="w-28"
            value={days}
            onChange={(e) => setDays(e.target.value)}
            required
          />
        </Field>
      </div>
      {method === "manual" ? (
        <ManualReview policyId={policyId} newsDays={newsDays} save={save} target={target} />
      ) : method !== null ? (
        <AiReview
          target={target}
          policyId={policyId}
          reviewerId={method}
          newsDays={newsDays}
          again={again}
          save={save}
        />
      ) : null}
      <p className="text-xs text-muted-foreground">
        <Trans
          i18nKey="reviews.pane.defaultIn"
          components={{ goto: <Link to="/settings" className="underline" /> }}
        />
      </p>
      <FormError error={options.error} />
    </div>
  );
}

/** REV-08: the AI reviewer runs in the background; the result fills in when it is ready. */
function AiReview({
  target,
  policyId,
  reviewerId,
  newsDays,
  again,
  save,
}: {
  target: ReviewTarget;
  policyId: number;
  reviewerId: number;
  newsDays: number;
  again: boolean;
  save: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const options = useReviewerOptions();
  const usage = useUsage(reviewerId);
  const start = useStartReview(policyId, target);
  const [saving, setSaving] = useState(false);
  const unavailable =
    usage.data?.unavailable_reason &&
    // NFR-10: the reason in the UI language, by its code
    translateMessage(
      usage.data.unavailable_code,
      usage.data.unavailable_params,
      usage.data.unavailable_reason,
    );
  const description = options.data?.find((o) => o.id === reviewerId)?.description;

  const submit = async () => {
    setSaving(true);
    try {
      await save();
      start.mutate({ reviewerId, newsDays });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-3">
      {/* NFR-01, NFR-15: what leaves the server, before anything is sent */}
      <p className="text-sm text-muted-foreground">
        {t("reviews.start.data")}
        {t("reviews.start.dataNothingElse")}
      </p>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          onClick={() => void submit()}
          disabled={saving || start.isPending || !!unavailable || !usage.data}
        >
          {target === "active"
            ? t("reviews.start.quick")
            : again
              ? t("reviews.start.again")
              : t("reviews.start.button")}
        </Button>
        {usage.data?.ai_reviewer_name && (
          <span className="text-sm text-muted-foreground">
            {t("reviews.start.usage", {
              used: usage.data.used,
              limit: usage.data.limit,
              name: usage.data.ai_reviewer_name,
            })}
          </span>
        )}
      </div>
      {unavailable && <Alert variant="warning">{unavailable}</Alert>}
      <FormError error={start.error ?? usage.error} />
    </div>
  );
}

/** REV-18, REV-19: copy the prompt into an AI outside the app and paste its answer back. */
function ManualReview({
  target,
  policyId,
  newsDays,
  save,
}: {
  target: ReviewTarget;
  policyId: number;
  newsDays: number;
  save: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const prompt = useReviewPrompt(policyId, target);
  const submit = useSubmitManualReview(policyId, target);
  const [copied, setCopied] = useState<"yes" | "failed" | null>(null);
  const [answer, setAnswer] = useState("");

  const copy = async () => {
    setCopied(null);
    await save();
    const { text } = await prompt.mutateAsync({ newsDays });
    try {
      await navigator.clipboard.writeText(text);
      setCopied("yes");
    } catch {
      setCopied("failed"); // e.g. plain HTTP in the LAN: the prompt is shown to copy by hand
    }
  };
  const send = (event: FormEvent) => {
    event.preventDefault();
    submit.mutate(answer, {
      onSuccess: () => {
        setAnswer("");
        setCopied(null);
      },
    });
  };
  const answerProblems =
    submit.error instanceof ApiError
      ? submit.error.problems.filter((p) => p.path === "answer")
      : [];

  return (
    <form className="grid gap-3" onSubmit={send} aria-label={t("reviews.pane.manualForm")}>
      <ol className="grid gap-4">
        <Step no={1}>
          {/* NFR-01, REV-19: what the prompt contains, before it is copied */}
          <p className="text-sm text-muted-foreground">{t("reviews.pane.data")}</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => void copy().catch(() => undefined)}
              disabled={prompt.isPending}
            >
              {t("reviews.pane.copy")}
            </Button>
            {copied === "yes" && (
              <span role="status" className="text-sm text-muted-foreground">
                {t("reviews.pane.copied")}
              </span>
            )}
          </div>
          {copied === "failed" && prompt.data && (
            <Field id="review-prompt" label={t("reviews.pane.copyFailed")}>
              <Textarea
                id="review-prompt"
                readOnly
                rows={6}
                value={prompt.data.text}
                onFocus={(e) => e.target.select()}
              />
            </Field>
          )}
          <FormError error={prompt.error} />
        </Step>
        <Step no={2}>
          <p className="text-sm">{t("reviews.pane.step2")}</p>
        </Step>
        <Step no={3}>
          <Field id="review-manual-answer" label={t("reviews.pane.answer")}>
            <Textarea
              id="review-manual-answer"
              rows={8}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              required
            />
          </Field>
          {answerProblems.length > 0 && (
            <Alert variant="destructive">
              <p className="font-medium">{t("reviews.pane.problems")}</p>
              <ul className="list-disc pl-5">
                {answerProblems.map((p) => (
                  <li key={p.message}>{p.message}</li>
                ))}
              </ul>
            </Alert>
          )}
          <FormError error={submit.error} fields={["answer"]} />
          <div>
            <Button type="submit" disabled={submit.isPending}>
              {t("reviews.pane.save")}
            </Button>
          </div>
        </Step>
      </ol>
    </form>
  );
}

/** One of the numbered steps of a manual review (REV-18). */
function Step({ no, children }: { no: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground"
      >
        {no}
      </span>
      <div className="grid min-w-0 flex-1 gap-2">{children}</div>
    </li>
  );
}
