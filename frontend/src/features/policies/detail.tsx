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
import { ReviewSection, activationWarning } from "@/features/reviews/review";
import { statusLabel } from "@/features/theses/status";
import { formatDateTime } from "@/lib/format";

import {
  policiesKey,
  targetImport,
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
  const [importing, setImporting] = useState(false);
  const [tab, setTab] = useState("structure");
  // Counts finished imports; remounts the version view so it shows the imported draft
  const [imports, setImports] = useState(0);

  if (policy.error) return <FormError error={policy.error} />;
  if (!policy.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const p = policy.data;
  const active = [...p.versions].reverse().find((v) => !v.is_draft && v.active_until === null);
  const draft = p.versions.find((v) => v.is_draft);
  const archived = p.archived_at !== null;
  const editDraft = () =>
    navigate({ to: "/policies/$policyId/draft", params: { policyId: String(p.id) } });
  const error =
    actions.createDraft.error ??
    actions.deleteDraft.error ??
    actions.adopt.error ??
    actions.archive.error;

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
            <Link
              to="/theses/$thesisId"
              params={{ thesisId: String(p.thesis_id) }}
              className="underline"
            >
              {t("policies.detail.thesis")}
            </Link>
          </div>
        </div>
        {!archived && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setImporting(true)}>
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
          <strong>{statusLabel(p.thesis_status ?? "")}</strong>
          {t("policies.detail.thesisWarningAfter")}
        </Alert>
      )}
      {p.newer_thesis_revision_id !== null && !archived && (
        <Alert variant="warning" className="flex flex-wrap items-center justify-between gap-2">
          <span>{t("policies.detail.newerRevision")}</span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => actions.adopt.mutate(undefined, { onSuccess: editDraft })}
          >
            {t("policies.detail.takeOver")}
          </Button>
        </Alert>
      )}
      <FormError error={error} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="structure">{t("policies.detail.tabStructure")}</TabsTrigger>
          <TabsTrigger value="versions">{t("policies.detail.tabVersions")}</TabsTrigger>
          <TabsTrigger value="compare" disabled={p.versions.length < 2}>
            {t("policies.detail.tabCompare")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="structure">
          <VersionView key={imports} policy={p} showDraft={imports > 0} />
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
        />
      )}
      {importing && (
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
          onClose={() => setImporting(false)}
          onDone={() => {
            setImporting(false);
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

function VersionView({ policy, showDraft }: { policy: Policy; showDraft: boolean }) {
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
        <Label htmlFor="version">{t("policies.version.label")}</Label>
        <NativeSelect
          id="version"
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
          href={`/api/policies/${policy.id}/versions/${versionNo}/export`}
          download
        >
          {t("policies.version.export")}
        </a>
      </div>
      {version.data && (
        <>
          <p className="text-sm text-muted-foreground">
            {t("policies.version.thesisRevision", {
              no: version.data.thesis_revision_no,
              status: statusLabel(version.data.thesis_status),
            })}
          </p>
          {version.data.positions.length === 0 ? (
            <p className="text-muted-foreground">{t("policies.version.noPositions")}</p>
          ) : (
            <PositionsTable version={version.data} />
          )}
        </>
      )}
      {summary && <ReviewSection key={summary.version_no} kind="policy" brief={summary.review} />}
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

function VersionList({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  return (
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
        </li>
      ))}
    </ol>
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
}: {
  policy: Policy;
  draftNo: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { activate } = usePolicyActions(policy.id);
  const [note, setNote] = useState("");
  const warning = activationWarning(policy.versions.find((v) => v.is_draft)?.review); // REV-11
  const submit = (event: FormEvent) => {
    event.preventDefault();
    activate.mutate(note.trim() || null, { onSuccess: onClose });
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
