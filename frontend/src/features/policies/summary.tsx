import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Field, FormError, fieldError } from "@/components/form";
import { Stars, formatScore } from "@/components/stars";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { isRunning, type ReviewBrief } from "@/features/reviews/api";
import { activationWarning } from "@/features/reviews/review";
import { SemaphoreBadge } from "@/features/reviews/semaphore";
import { formatPct } from "@/lib/format";

import {
  useCompare,
  usePolicy,
  usePolicyActions,
  useVersion,
  type Policy,
  type Version,
} from "./api";
import { DiscardDraft } from "./discard";
import { VersionDiffView } from "./positions";

const TOLERANCE = 0.01; // POL-05

/** POL-17: the summary of the draft, from which it is activated. Reviews are pointed out,
 * never required (REV-11); the target structure must be complete (POL-05). */
export function DraftSummaryPage({ policyId }: { policyId: number }) {
  const { t } = useTranslation();
  const policy = usePolicy(policyId);
  const draftSummary = policy.data?.versions.find((v) => v.is_draft);
  const version = useVersion(policyId, draftSummary?.version_no);
  if (policy.data && !draftSummary) return <Alert>{t("policies.editor.noDraft")}</Alert>;
  if (!policy.data || !version.data || !draftSummary) {
    return <p className="text-muted-foreground">{t("common.loading")}</p>;
  }
  return <Summary policy={policy.data} draft={version.data} brief={draftSummary.review} />;
}

function Summary({
  policy,
  draft,
  brief,
}: {
  policy: Policy;
  draft: Version;
  brief: ReviewBrief | null | undefined;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activate, saveChangeNote } = usePolicyActions(policy.id);
  const active = [...policy.versions].reverse().find((v) => !v.is_draft && v.active_until === null);
  const [note, setNote] = useState(draft.change_note ?? "");
  const saved = useRef(draft.change_note ?? "");

  // POL-14: the change note is saved automatically as well
  useEffect(() => {
    if (note === saved.current) return;
    const timer = setTimeout(() => {
      saved.current = note;
      saveChangeNote.mutate(note.trim() || null);
    }, 800);
    return () => clearTimeout(timer);
  }, [note, saveChangeNote]);

  const total = draft.positions.reduce((sum, p) => sum + Number(p.target_pct), 0);
  const cashBuffers = draft.positions.filter((p) => p.type === "cash_buffer").length;
  const complete = Math.abs(total - 100) <= TOLERANCE && cashBuffers <= 1;
  const warning = activationWarning(brief);
  const running = isRunning(brief?.state);
  const editor = { to: "/policies/$policyId/draft", params: { policyId: String(policy.id) } };

  const submit = () =>
    activate.mutate(note.trim() || null, {
      onSuccess: () =>
        void navigate({ to: "/policies/$policyId", params: { policyId: String(policy.id) } }),
    });

  return (
    <div className="grid max-w-3xl gap-4">
      <div className="grid gap-1">
        <Link {...editor} className="text-sm underline">
          {t("policies.summary.back")}
        </Link>
        <h1 className="text-2xl font-semibold">
          {t("policies.summary.title", { name: policy.name, no: draft.version_no })}
        </h1>
      </div>

      <Card>
        <CardContent className="grid gap-3 pt-5">
          <h2 className="font-semibold">{t("policies.summary.review")}</h2>
          <ReviewState brief={brief} />
          {brief?.semaphore === "broken" && (
            <Alert variant="warning">{t("policies.summary.broken")}</Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-2 pt-5">
          <h2 className="font-semibold">{t("policies.summary.structure")}</h2>
          <p
            className={Math.abs(total - 100) <= TOLERANCE ? "text-sm" : "text-sm text-destructive"}
          >
            {t("policies.summary.total", { total: formatPct(total, undefined, 2) })}
          </p>
          {cashBuffers > 1 && (
            <p className="text-sm text-destructive">{t("policies.editor.oneCashBuffer")}</p>
          )}
          {!complete && <Alert variant="destructive">{t("policies.summary.incomplete")}</Alert>}
        </CardContent>
      </Card>

      {active && <Changes policyId={policy.id} from={active.version_no} to={draft.version_no} />}

      <Card>
        <CardContent className="grid gap-2 pt-5">
          <h2 className="font-semibold">{t("policies.summary.portfolios")}</h2>
          <p className="text-sm">
            {t("policies.activate.fixed")}{" "}
            {policy.portfolios.length > 0
              ? t("policies.activate.appliesTo", {
                  portfolios: policy.portfolios.map((p) => p.name).join(", "),
                })
              : t("policies.activate.noPortfolio")}
          </p>
        </CardContent>
      </Card>

      <Field
        id="change-note"
        label={
          draft.version_no > 1
            ? t("policies.activate.changeNote")
            : t("policies.activate.changeNoteOptional")
        }
        error={fieldError(activate.error, "change_note")}
      >
        <Input id="change-note" value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>

      {warning && !running && <Alert variant="warning">{warning}</Alert>}
      {running && <Alert>{t("policies.summary.running")}</Alert>}
      <FormError error={activate.error ?? saveChangeNote.error} fields={["change_note"]} />

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <DiscardDraft
          policyId={policy.id}
          neverActivated={!active && policy.versions.length === 1}
        />
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link {...editor}>{t("policies.summary.toEditor")}</Link>
          </Button>
          <Button
            type="button"
            onClick={submit}
            disabled={activate.isPending || running || !complete}
          >
            {warning ? t("policies.activate.activateAnyway") : t("policies.activate.activate")}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** REV-09, REV-11: the review's score and semaphore, and whether it matches the draft. */
function ReviewState({ brief }: { brief: ReviewBrief | null | undefined }) {
  const { t } = useTranslation();
  if (!brief || brief.state === "failed") {
    return <p className="text-sm">{t("policies.summary.noReview")}</p>;
  }
  if (isRunning(brief.state)) return <p className="text-sm">{t("policies.summary.running")}</p>;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {brief.total !== null && (
        <>
          <Stars score={brief.total} label={t("reviews.score.totalLabel")} />
          <span className="font-semibold tabular-nums">{formatScore(brief.total)}</span>
        </>
      )}
      <SemaphoreBadge semaphore={brief.semaphore} />
      {brief.outdated ? (
        <Badge variant="warning">{t("policies.summary.doesNotMatch")}</Badge>
      ) : (
        <Badge variant="success">{t("policies.summary.matches")}</Badge>
      )}
    </div>
  );
}

/** POL-09: what the draft changes against the active version. */
function Changes({ policyId, from, to }: { policyId: number; from: number; to: number }) {
  const { t } = useTranslation();
  const diff = useCompare(policyId, from, to);
  return (
    <Card>
      <CardContent className="grid gap-2 pt-5">
        <h2 className="font-semibold">{t("policies.summary.changes", { no: from })}</h2>
        {diff.data && <VersionDiffView diff={diff.data} />}
      </CardContent>
    </Card>
  );
}
