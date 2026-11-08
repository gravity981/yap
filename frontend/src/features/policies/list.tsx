import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Trans, useTranslation } from "react-i18next";

import { FileImport } from "@/components/file-import";
import { Field, FormError, fieldError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SemaphoreBadge } from "@/features/reviews/semaphore";
import { thesisTemplate } from "@/features/theses/template";
import { formatDateTime } from "@/lib/format";

import {
  policiesKey,
  thesisImport,
  useCreatePolicy,
  usePolicies,
  usePolicyActions,
  type PolicySummary,
} from "./api";
import { DiscardDraft } from "./discard";
import { PolicyFacts, SharingBadge } from "./policy-parts";
import { MarkBadge } from "./mark";

/** POL-01, POL-12 */
export function PoliciesPage() {
  const { t } = useTranslation();
  const policies = usePolicies();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle title={t("policies.list.title")} description={t("policies.list.description")} />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setImporting(true)}>
            {t("policies.list.importThesis")}
          </Button>
          <Button onClick={() => setCreating(true)}>{t("policies.list.newPolicy")}</Button>
        </div>
      </div>
      <FormError error={policies.error} />
      {policies.data?.length === 0 && (
        <p className="text-muted-foreground">{t("policies.list.empty")}</p>
      )}
      {policies.data && policies.data.length > 0 && (
        <ul className="grid gap-3">
          {policies.data.map((p) => (
            <PolicyCard key={p.id} policy={p} />
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">{t("policies.list.legend")}</p>
      {creating && <NewPolicyDialog onClose={() => setCreating(false)} />}
      {importing && (
        <FileImport
          title={t("policies.list.importThesisTitle")}
          description={t("policies.list.importThesisDescription")}
          preview={(text) => thesisImport.preview(text)}
          run={(text) => thesisImport.runNew(text)}
          renderPreview={(preview) => (
            <p>
              <Trans
                i18nKey="policies.list.importThesisPreview"
                values={{ title: preview.title }}
                components={{ strong: <strong /> }}
              />
            </p>
          )}
          onClose={() => setImporting(false)}
          onDone={(policy) => {
            setImporting(false);
            void client.invalidateQueries({ queryKey: policiesKey });
            void navigate({ to: "/policies/$policyId", params: { policyId: String(policy.id) } });
          }}
        />
      )}
    </div>
  );
}

function NewPolicyDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const create = useCreatePolicy();
  const navigate = useNavigate();
  const [name, setName] = useState("");

  // POL-01: draft v1 starts with the thesis template; the editor opens right away
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { name, thesis_md: thesisTemplate() },
      {
        onSuccess: (p) =>
          navigate({ to: "/policies/$policyId/draft", params: { policyId: String(p.id) } }),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{t("policies.create.title")}</DialogTitle>
        <DialogDescription>{t("policies.create.description")}</DialogDescription>
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          <Field
            id="policy-name"
            label={t("policies.create.name")}
            error={fieldError(create.error, "name")}
          >
            <Input
              id="policy-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </Field>
          <FormError error={create.error} fields={["name"]} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {t("policies.create.create")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** POL-19: a policy with its active version, score, semaphore, dates, portfolios, sharing
 * level and marks, and its draft with the actions to continue or discard it. */
function PolicyCard({ policy: p }: { policy: PolicySummary }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { createDraft } = usePolicyActions(p.id);
  const editor = { to: "/policies/$policyId/draft", params: { policyId: String(p.id) } } as const;
  const draftReview = p.draft?.review;
  const draftState = !draftReview
    ? t("policies.list.draftNotReviewed")
    : draftReview.state === "queued" || draftReview.state === "running"
      ? t("policies.list.draftReviewRunning")
      : draftReview.state === "failed"
        ? t("policies.list.draftReviewFailed")
        : draftReview.outdated
          ? t("reviews.result.noLongerMatches")
          : t("reviews.result.matches");
  return (
    <li
      className="flex flex-wrap items-center gap-4 rounded-lg border bg-card p-4"
      aria-label={p.name}
    >
      <div className="grid min-w-0 flex-[1_1_20rem] gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/policies/$policyId"
            params={{ policyId: String(p.id) }}
            className="text-lg font-semibold hover:underline"
          >
            {p.name}
          </Link>
          {p.active_version_no !== null ? (
            <Badge variant="success">
              {t("policies.list.activeBadge", { no: p.active_version_no })}
            </Badge>
          ) : (
            p.draft && (
              <Badge variant="outline">
                {t("policies.list.draftBadgeNo", { no: p.draft.version_no })}
              </Badge>
            )
          )}
          {p.active_version_no !== null && <SemaphoreBadge semaphore={p.semaphore} />}
          <MarkBadge mark={p.mark} />
          <SharingBadge sharing={p.sharing} />
          {p.archived_at && <Badge variant="secondary">{t("policies.list.archived")}</Badge>}
        </div>
        {p.active_version_no !== null ? (
          <PolicyFacts policy={p} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("policies.list.notActiveYet")}</p>
        )}
      </div>
      {p.draft ? (
        <div className="grid flex-[1_1_16rem] gap-1 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
          <span className="font-medium">
            {t("policies.list.draftInProgress", { no: p.draft.version_no })}
          </span>
          <span className="text-muted-foreground">
            {[
              p.draft.positions === 0 && t("policies.list.textOnly"),
              draftState,
              p.draft.updated_at &&
                t("policies.list.savedAt", { date: formatDateTime(p.draft.updated_at) }),
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      ) : (
        !p.archived_at && (
          <p className="flex-[1_1_16rem] text-sm text-muted-foreground">
            {t("policies.list.noDraft")}
          </p>
        )
      )}
      {!p.archived_at && (
        <div className="grid gap-1">
          {p.draft ? (
            <>
              <Button asChild>
                <Link {...editor}>{t("policies.list.continueDraft")}</Link>
              </Button>
              <DiscardDraft policyId={p.id} neverActivated={p.active_version_no === null} />
            </>
          ) : (
            <Button
              variant="outline"
              onClick={() =>
                createDraft.mutate(undefined, { onSuccess: () => void navigate(editor) })
              }
              disabled={createDraft.isPending}
            >
              {t("policies.list.newVersion")}
            </Button>
          )}
        </div>
      )}
    </li>
  );
}
