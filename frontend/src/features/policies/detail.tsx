import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Trans, useTranslation } from "react-i18next";

import { FileImport } from "@/components/file-import";
import { filePositions, ImportPriceSources } from "@/features/prices/import-price-sources";
import { Field, FormError, fieldError } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Markdown } from "@/components/markdown";
import {
  ReviewBriefLine,
  ReviewSection,
  activationWarning,
  reviewTitle,
} from "@/features/reviews/review";
import { ScoreCourse } from "@/features/reviews/score-course";
import { SemaphoreBadge, semaphoreLabel } from "@/features/reviews/semaphore";
import { formatDateTime } from "@/lib/format";

import {
  policiesKey,
  targetImport,
  thesisImport,
  useCompare,
  usePolicy,
  usePolicyActions,
  useVersion,
  type Policy,
} from "./api";
import { PositionsTable, VersionDiffView } from "./positions";

/** POL-08 to POL-13: versions, draft, warnings, comparison. */
export function PolicyPage({ policyId }: { policyId: number }) {
  const { t } = useTranslation();
  const policy = usePolicy(policyId);
  const actions = usePolicyActions(policyId);
  const navigate = useNavigate();
  const client = useQueryClient();
  const [activating, setActivating] = useState(false);
  const [importing, setImporting] = useState<"target" | "thesis" | null>(null);
  const [tab, setTab] = useState("thesis");
  // Counts finished imports and activations; remounts the version view so it shows the
  // imported draft or the newly active version
  const [imports, setImports] = useState(0);

  if (policy.error) return <FormError error={policy.error} />;
  if (!policy.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const p = policy.data;
  const active = [...p.versions].reverse().find((v) => !v.is_draft && v.active_until === null);
  const draft = p.versions.find((v) => v.is_draft);
  const archived = p.archived_at !== null;
  const editDraft = () =>
    navigate({ to: "/policies/$policyId/draft", params: { policyId: String(p.id) } });
  const error = actions.createDraft.error ?? actions.deleteDraft.error ?? actions.archive.error;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">{p.name}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {active ? (
              <span>{t("policies.detail.active", { label: active.label })}</span>
            ) : (
              <span>{t("policies.detail.noActive")}</span>
            )}
            {draft && (
              <Badge variant="outline">
                {t("policies.detail.draftVersion", { no: draft.version_no })}
              </Badge>
            )}
            {archived && <Badge variant="secondary">{t("policies.detail.archived")}</Badge>}
          </div>
        </div>
        {!archived && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setImporting("thesis")}>
              {t("policies.detail.importThesis")}
            </Button>
            <Button variant="outline" onClick={() => setImporting("target")}>
              {t("policies.detail.importTarget")}
            </Button>
            {draft ? (
              <>
                <Button variant="outline" onClick={editDraft}>
                  {t("policies.detail.editDraft")}
                </Button>
                <Button onClick={() => setActivating(true)}>
                  {t("policies.detail.activateDraft")}
                </Button>
              </>
            ) : (
              <Button
                onClick={() => actions.createDraft.mutate(undefined, { onSuccess: editDraft })}
              >
                {t("policies.detail.newDraft")}
              </Button>
            )}
          </div>
        )}
      </div>

      {p.thesis_warning && (
        <Alert variant="warning">
          {t("policies.detail.thesisWarningBefore")}
          <strong>{semaphoreLabel(p.semaphore)}</strong>
          {t("policies.detail.thesisWarningAfter")}
        </Alert>
      )}
      <FormError error={error} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="thesis">{t("policies.detail.tabThesis")}</TabsTrigger>
          <TabsTrigger value="structure">{t("policies.detail.tabStructure")}</TabsTrigger>
          <TabsTrigger value="versions">{t("policies.detail.tabVersions")}</TabsTrigger>
          <TabsTrigger value="compare" disabled={p.versions.length < 2}>
            {t("policies.detail.tabCompare")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="thesis">
          <VersionView key={imports} policy={p} part="thesis" showDraft={imports > 0} />
        </TabsContent>
        <TabsContent value="structure">
          <VersionView key={imports} policy={p} part="structure" showDraft={imports > 0} />
        </TabsContent>
        <TabsContent value="versions" className="grid gap-4">
          <VersionList policy={p} />
          {draft && !archived && (
            <div>
              <Button
                variant="outline"
                onClick={() => actions.deleteDraft.mutate(undefined)}
                disabled={draft.version_no === 1}
                title={
                  draft.version_no === 1 ? t("policies.detail.firstCannotBeDeleted") : undefined
                }
              >
                {t("policies.detail.deleteDraft")}
              </Button>
            </div>
          )}
          <PortfoliosUsing
            policy={p}
            onArchive={() => actions.archive.mutate(undefined)}
            archived={archived}
          />
        </TabsContent>
        <TabsContent value="compare">
          <CompareVersions policy={p} />
        </TabsContent>
      </Tabs>

      {activating && draft && (
        <ActivateDialog
          policy={p}
          draftNo={draft.version_no}
          onClose={() => setActivating(false)}
          // Shows the version that is active now, not the one selected before
          onActivated={() => {
            setActivating(false);
            setImports((n) => n + 1);
          }}
        />
      )}
      {importing === "thesis" && (
        <FileImport
          title={t("policies.detail.importThesis")}
          description={t("policies.detail.importDescription", { name: p.name })}
          preview={(text) => thesisImport.preview(text, p.id)}
          run={(text) => thesisImport.runIntoDraft(text, p.id)}
          renderPreview={(preview) => (
            <p className="text-sm">
              {t("policies.detail.importThesisPreview", {
                title: preview.title,
                no: preview.version_no,
              })}
            </p>
          )}
          onClose={() => setImporting(null)}
          onDone={() => {
            setImporting(null);
            setTab("thesis");
            void client
              .invalidateQueries({ queryKey: policiesKey })
              .then(() => setImports((n) => n + 1));
          }}
        />
      )}
      {importing === "target" && (
        <FileImport
          title={t("policies.detail.importTarget")}
          description={t("policies.detail.importDescription", { name: p.name })}
          preview={async (text) => ({
            diff: await targetImport.preview(text, p.id),
            positions: filePositions(text),
          })}
          run={(text) => targetImport.run(text, p.id)}
          renderPreview={({ diff, positions }) => (
            <div className="grid gap-4">
              <div className="grid gap-2">
                <p className="text-sm">{t("policies.detail.importChanges")}</p>
                <VersionDiffView diff={diff} />
              </div>
              <ImportPriceSources positions={positions} />
            </div>
          )}
          onClose={() => setImporting(null)}
          onDone={() => {
            setImporting(null);
            setTab("structure");
            // Like the other policy changes; the import may add tickers to the catalog
            for (const key of [["assets"], ["portfolios"], ["timeline"]]) {
              void client.invalidateQueries({ queryKey: key });
            }
            // After the refetch, the policy contains the draft the import wrote
            void client
              .invalidateQueries({ queryKey: policiesKey })
              .then(() => setImports((n) => n + 1));
          }}
        />
      )}
    </div>
  );
}

/** One version of the policy: its thesis (THS-01) or its target structure (POL-02), each
 * with its review. */
function VersionView({
  policy,
  part,
  showDraft,
}: {
  policy: Policy;
  part: "thesis" | "structure";
  showDraft: boolean;
}) {
  const { t } = useTranslation();
  const newest = policy.versions.at(-1)!.version_no;
  const draft = policy.versions.find((v) => v.is_draft);
  const [versionNo, setVersionNo] = useState(
    (showDraft ? draft?.version_no : undefined) ??
      [...policy.versions].reverse().find((v) => !v.is_draft && v.active_until === null)
        ?.version_no ??
      newest,
  );
  const version = useVersion(policy.id, versionNo);
  const summary = policy.versions.find((v) => v.version_no === versionNo);
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor={`${part}-version`}>{t("policies.version.label")}</Label>
        <NativeSelect
          id={`${part}-version`}
          className="w-auto"
          value={versionNo}
          onChange={(e) => setVersionNo(Number(e.target.value))}
        >
          {[...policy.versions].reverse().map((v) => (
            <option key={v.version_no} value={v.version_no}>
              {v.label}
              {v.is_draft
                ? t("policies.version.draftSuffix")
                : v.active_until === null
                  ? t("policies.version.activeSuffix")
                  : ""}
            </option>
          ))}
        </NativeSelect>
        <a
          className="text-sm underline"
          href={
            part === "thesis"
              ? `/api/policies/${policy.id}/versions/${versionNo}/thesis/export`
              : `/api/policies/${policy.id}/versions/${versionNo}/export`
          }
          download
        >
          {t("policies.version.export")}
        </a>
      </div>
      {version.data &&
        (part === "thesis" ? (
          <div className="grid gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{version.data.thesis_title}</h2>
              {/* THS-04: the semaphore comes from the version's review */}
              <SemaphoreBadge semaphore={summary?.review?.semaphore} />
            </div>
            <div className="rounded-md border p-4">
              <Markdown source={version.data.thesis_md} />
            </div>
          </div>
        ) : version.data.positions.length === 0 ? (
          <p className="text-muted-foreground">{t("policies.version.noPositions")}</p>
        ) : (
          <PositionsTable version={version.data} />
        ))}
      {/* REV-02: one review of thesis and target structure; versions from before stage 2
          may have a thesis and a policy review */}
      {summary &&
        (summary.reviews.length === 0 ? (
          <ReviewSection key={summary.version_no} brief={null} />
        ) : (
          summary.reviews.map((r) => (
            <ReviewSection key={`${summary.version_no}-${r.id}`} brief={r} />
          ))
        ))}
      {/* REV-01: reviews are made in the draft editor */}
      {summary?.is_draft && policy.archived_at === null && (
        <p className="text-sm text-muted-foreground">
          <Trans
            i18nKey="reviews.pane.inEditor"
            components={{
              goto: (
                <Link
                  to="/policies/$policyId/draft"
                  params={{ policyId: String(policy.id) }}
                  className="underline"
                />
              ),
            }}
          />
        </p>
      )}
    </div>
  );
}

/** POL-12, THS-08: the versions with their reviews and the course of the review score. */
function VersionList({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-4">
      <ScoreCourse
        points={policy.versions
          .filter((v) => !v.is_draft && v.review?.state === "done" && v.review.total !== null)
          .map((v) => ({
            label: v.label,
            date: v.active_from ?? "",
            score: v.review!.total!,
            version: v.review!.scoring_version,
          }))}
      />
      <ol className="grid gap-2">
        {[...policy.versions].reverse().map((v) => (
          <li key={v.version_no} className="rounded-md border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{v.label}</span>
              {v.is_draft ? (
                <Badge variant="outline">{t("policies.version.draft")}</Badge>
              ) : v.active_until === null ? (
                <Badge variant="success">{t("policies.version.active")}</Badge>
              ) : null}
              {v.active_from && (
                <span className="text-muted-foreground">
                  {formatDateTime(v.active_from)}
                  {v.active_until && ` – ${formatDateTime(v.active_until)}`}
                </span>
              )}
            </div>
            {v.change_note && <p className="mt-1">{v.change_note}</p>}
            {v.reviews.length > 0 && (
              <div className="mt-2 grid gap-1">
                {v.reviews.map((r) => (
                  <span key={r.id} className="flex flex-wrap items-center gap-2">
                    <span className="text-muted-foreground">{reviewTitle(r.kind)}:</span>
                    <ReviewBriefLine brief={r} />
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PortfoliosUsing({
  policy,
  onArchive,
  archived,
}: {
  policy: Policy;
  onArchive: () => void;
  archived: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-2">
      <h2 className="font-semibold">{t("policies.portfolios.title")}</h2>
      {policy.portfolios.length === 0 ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {t("policies.portfolios.none")}
          {!archived && (
            <Button size="sm" variant="outline" onClick={onArchive}>
              {t("policies.portfolios.archive")}
            </Button>
          )}
        </div>
      ) : (
        <ul className="list-disc pl-5 text-sm">
          {policy.portfolios.map((p) => (
            <li key={p.id}>{p.name}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CompareVersions({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  const numbers = policy.versions.map((v) => v.version_no);
  const [from, setFrom] = useState(numbers.at(-2) ?? 1);
  const [to, setTo] = useState(numbers.at(-1) ?? 1);
  const diff = useCompare(policy.id, from, to);
  const fromId = "from-version";
  const toId = "to-version";
  const select = (id: string, value: number, set: (v: number) => void) => (
    <NativeSelect
      id={id}
      className="w-auto"
      value={value}
      onChange={(e) => set(Number(e.target.value))}
    >
      {numbers.map((n) => (
        <option key={n} value={n}>
          {t("policies.compare.option", { no: n })}
        </option>
      ))}
    </NativeSelect>
  );
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor={fromId}>{t("policies.compare.from")}</Label>
        {select(fromId, from, setFrom)}
        <Label htmlFor={toId}>{t("policies.compare.to")}</Label>
        {select(toId, to, setTo)}
      </div>
      {diff.data && <VersionDiffView diff={diff.data} />}
    </div>
  );
}

/** POL-06 to POL-08: activation takes effect now and applies to all listed portfolios. */
function ActivateDialog({
  policy,
  draftNo,
  onClose,
  onActivated,
}: {
  policy: Policy;
  draftNo: number;
  onClose: () => void;
  onActivated: () => void;
}) {
  const { t } = useTranslation();
  const { activate } = usePolicyActions(policy.id);
  const [note, setNote] = useState("");
  // REV-11: the review of the draft
  const draft = policy.versions.find((v) => v.is_draft);
  const warning = activationWarning(draft?.review);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    activate.mutate(note.trim() || null, { onSuccess: onActivated });
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>
          {t("policies.activate.title", { name: policy.name, no: draftNo })}
        </DialogTitle>
        <DialogDescription>
          {t("policies.activate.fixed")}{" "}
          {policy.portfolios.length > 0
            ? t("policies.activate.appliesTo", {
                portfolios: policy.portfolios.map((p) => p.name).join(", "),
              })
            : t("policies.activate.noPortfolio")}
        </DialogDescription>
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          {warning && <Alert variant="warning">{warning}</Alert>}
          <Field
            id="activation-note"
            label={
              draftNo > 1
                ? t("policies.activate.changeNote")
                : t("policies.activate.changeNoteOptional")
            }
            error={fieldError(activate.error, "change_note")}
          >
            <Input
              id="activation-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required={draftNo > 1}
            />
          </Field>
          <FormError error={activate.error} fields={["change_note"]} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={activate.isPending}>
              {warning ? t("policies.activate.activateAnyway") : t("policies.activate.activate")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
