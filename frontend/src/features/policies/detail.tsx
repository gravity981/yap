import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";

import { FileImport } from "@/components/file-import";
import { filePositions, ImportPriceSources } from "@/features/prices/import-price-sources";
import { FormError } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Markdown } from "@/components/markdown";
import { ReviewBriefLine, ReviewSection, reviewTitle } from "@/features/reviews/review";
import { ReviewLog } from "@/features/reviews/review-log";
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
import { DiscardDraft } from "./discard";
import {
  DraftReview,
  PolicyFacts,
  PolicyName,
  ReviewAgain,
  Sharing,
  SharingBadge,
} from "./policy-parts";
import { MarkBadge } from "./mark";
import { PositionsTable, VersionDiffView } from "./positions";

/** POL-08 to POL-13: versions, draft, warnings, comparison. */
export function PolicyPage({ policyId }: { policyId: number }) {
  const { t } = useTranslation();
  const policy = usePolicy(policyId);
  const actions = usePolicyActions(policyId);
  const navigate = useNavigate();
  const client = useQueryClient();
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
  const error = actions.createDraft.error ?? actions.archive.error;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <Link to="/policies" className="text-sm underline">
            {t("policies.detail.back")}
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <PolicyName policy={p} />
            {/* THS-04, POL-11, REV-20, POL-18 */}
            {active && <SemaphoreBadge semaphore={p.semaphore} />}
            <MarkBadge mark={p.mark} />
            <SharingBadge sharing={p.sharing} />
          </div>
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
          <PolicyFacts policy={p} />
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
                  {t("policies.list.continueDraft")}
                </Button>
                {/* POL-17: activation goes through the summary of the draft */}
                <Button
                  onClick={() =>
                    void navigate({
                      to: "/policies/$policyId/draft/summary",
                      params: { policyId: String(p.id) },
                    })
                  }
                >
                  {t("policies.detail.finalize")}
                </Button>
              </>
            ) : (
              <Button
                onClick={() => actions.createDraft.mutate(undefined, { onSuccess: editDraft })}
              >
                {t("policies.list.newVersion")}
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

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Tabs value={tab} onValueChange={setTab} className="min-w-0">
          <TabsList className="flex-wrap">
            <TabsTrigger value="thesis">{t("policies.detail.tabThesis")}</TabsTrigger>
            <TabsTrigger value="structure">{t("policies.detail.tabStructure")}</TabsTrigger>
            <TabsTrigger value="reviews">{t("policies.detail.tabReviews")}</TabsTrigger>
            <TabsTrigger value="versions">{t("policies.detail.tabVersions")}</TabsTrigger>
          </TabsList>
          <TabsContent value="thesis">
            <VersionView
              key={`${imports}-${active?.version_no ?? 0}`}
              policy={p}
              part="thesis"
              showDraft={imports > 0}
            />
          </TabsContent>
          <TabsContent value="structure">
            <VersionView
              key={`${imports}-${active?.version_no ?? 0}`}
              policy={p}
              part="structure"
              showDraft={imports > 0}
            />
          </TabsContent>
          <TabsContent value="reviews">
            {/* REV-23, THS-08 */}
            <ReviewLog policyId={p.id} />
          </TabsContent>
          <TabsContent value="versions" className="grid gap-4">
            <VersionList policy={p} />
            {/* POL-09: any two versions, including the draft */}
            {p.versions.length > 1 && <CompareVersions policy={p} />}
            {draft && !archived && (
              <div>
                <DiscardDraft
                  policyId={p.id}
                  neverActivated={!active}
                  onDiscarded={() => setImports((n) => n + 1)}
                />
              </div>
            )}
            <PortfoliosUsing
              policy={p}
              onArchive={() => actions.archive.mutate(undefined)}
              archived={archived}
            />
          </TabsContent>
        </Tabs>
        {active && !archived && (
          <aside className="grid min-w-0 gap-4">
            {/* POL-22: a draft with changes has its own review; the active version is
                reviewed again when there is none, or the draft is the same version */}
            {p.draft?.changed ? (
              <DraftReview policy={p} />
            ) : (
              <ReviewAgain policy={p} versionLabel={active.label} />
            )}
            <Sharing policy={p} />
          </aside>
        )}
      </div>

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
      {/* REV-21: the latest review of the version; all of them are in the review log */}
      {summary && <ReviewSection key={summary.version_no} brief={summary.review} />}
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

/** POL-12, THS-08: the versions with their activation periods, change notes, marks and
 * latest review; the course of the score is in the review log (REV-23). */
function VersionList({ policy }: { policy: Policy }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-4">
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
              <MarkBadge mark={v.mark} />
              {v.active_from && (
                <span className="text-muted-foreground">
                  {formatDateTime(v.active_from)}
                  {v.active_until && ` – ${formatDateTime(v.active_until)}`}
                </span>
              )}
            </div>
            {v.change_note && <p className="mt-1">{v.change_note}</p>}
            {v.review && (
              <span className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground">{reviewTitle(v.review.kind)}:</span>
                <ReviewBriefLine brief={v.review} />
              </span>
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
