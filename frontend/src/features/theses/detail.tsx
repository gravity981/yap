import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Trans, useTranslation } from "react-i18next";

import { DiffView } from "@/components/diff-view";
import { FileImport } from "@/components/file-import";
import { Field, FormError, fieldError } from "@/components/form";
import { Markdown } from "@/components/markdown";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ReviewBriefLine, ReviewSection, activationWarning } from "@/features/reviews/review";
import { ScoreCourse } from "@/features/reviews/score-course";
import { formatDateTime } from "@/lib/format";

import {
  thesesKey,
  thesisImport,
  useCopyThesis,
  useRevision,
  useRevisionDiff,
  useSetVisibility,
  useThesis,
  useThesisDraft,
  type Thesis,
} from "./api";
import { useVisibilityLabel } from "./list";
import { statusLabel, ThesisStatusBadge } from "./status";

/** Content of a revision, its history (THS-08) and a comparison (THS-02). */
export function ThesisPage({ thesisId }: { thesisId: number }) {
  const { t } = useTranslation();
  const visibilityLabel = useVisibilityLabel();
  const thesis = useThesis(thesisId);
  const [revisionNo, setRevisionNo] = useState<number | undefined>(undefined);
  const [tab, setTab] = useState("content");
  const latest = thesis.data?.revisions.at(-1);
  const shown = revisionNo ?? latest?.revision_no;
  const revision = useRevision(thesisId, shown);
  const shownRevision = thesis.data?.revisions.find((r) => r.revision_no === shown);

  if (thesis.error) return <FormError error={thesis.error} />;
  if (!thesis.data || !latest)
    return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const th = thesis.data;
  // The header shows the latest activated revision; the draft is only its owner's
  const active = [...th.revisions].reverse().find((r) => !r.is_draft);
  const draft = th.revisions.find((r) => r.is_draft);
  const current = active ?? latest;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">{current.title}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <ThesisStatusBadge status={current.status} />
            <Badge variant="outline">{visibilityLabel(th.visibility)}</Badge>
            {!th.is_own && <Badge variant="outline">{t("theses.detail.sharedWithYou")}</Badge>}
            {active ? (
              <span>{t("theses.detail.revision", { no: active.revision_no })}</span>
            ) : (
              <span>{t("theses.detail.notActivated")}</span>
            )}
            {draft && (
              <Badge variant="outline">
                {t("theses.detail.draftBadge", { no: draft.revision_no })}
              </Badge>
            )}
          </div>
        </div>
        <Actions
          thesis={th}
          onImported={(no) => {
            setRevisionNo(no);
            setTab("content");
          }}
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="content">{t("theses.detail.tabContent")}</TabsTrigger>
          <TabsTrigger value="history">{t("theses.detail.tabHistory")}</TabsTrigger>
          <TabsTrigger value="compare" disabled={th.revisions.length < 2}>
            {t("theses.detail.tabCompare")}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="content" className="grid gap-3">
          {th.revisions.length > 1 && (
            <div className="flex items-center gap-2">
              <Label htmlFor="revision">{t("theses.detail.revisionLabel")}</Label>
              <NativeSelect
                id="revision"
                className="w-auto"
                value={shown}
                onChange={(e) => setRevisionNo(Number(e.target.value))}
              >
                {[...th.revisions].reverse().map((r) => (
                  <option key={r.revision_no} value={r.revision_no}>
                    {t("theses.detail.revisionOption", {
                      no: r.revision_no,
                      when: r.is_draft
                        ? t("theses.detail.draft")
                        : formatDateTime(r.activated_at ?? r.created_at),
                    })}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}
          <Card>
            <CardContent className="pt-5">
              {revision.data ? (
                <Markdown source={revision.data.content_md} />
              ) : (
                <p>{t("common.loading")}</p>
              )}
            </CardContent>
          </Card>
          <a
            className="text-sm underline"
            href={`/api/theses/${th.id}/revisions/${shown}/export`}
            download
          >
            {t("theses.detail.export", { no: shown })}
          </a>
          {shownRevision && (
            <ReviewSection
              key={shownRevision.revision_no}
              kind="thesis"
              ownerId={th.id}
              brief={shownRevision.review}
              canStart={false}
            />
          )}
          {/* REV-01: reviews are made in the draft editor */}
          {shownRevision?.is_draft && th.is_own && (
            <p className="text-sm text-muted-foreground">
              <Trans
                i18nKey="reviews.pane.inEditor"
                components={{
                  goto: (
                    <Link
                      to="/theses/$thesisId/edit"
                      params={{ thesisId: String(th.id) }}
                      className="underline"
                    />
                  ),
                }}
              />
            </p>
          )}
        </TabsContent>
        <TabsContent value="history" className="grid gap-4">
          <ScoreCourse
            points={th.revisions
              .filter((r) => !r.is_draft && r.review?.state === "done" && r.review.total !== null)
              .map((r) => ({
                label: t("theses.detail.revisionTitle", { no: r.revision_no }),
                date: r.activated_at ?? r.created_at,
                score: r.review!.total!,
                version: r.review!.scoring_version,
              }))}
          />
          <ol className="grid gap-3">
            {[...th.revisions].reverse().map((r) => (
              <li key={r.revision_no} className="rounded-md border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {t("theses.detail.revisionTitle", { no: r.revision_no })}
                  </span>
                  <ThesisStatusBadge status={r.status} />
                  {r.is_draft ? (
                    <Badge variant="outline">{t("theses.detail.draft")}</Badge>
                  ) : (
                    <span className="text-sm text-muted-foreground">
                      {formatDateTime(r.activated_at ?? r.created_at)}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm">
                  {r.change_note ??
                    (r.revision_no === 1
                      ? t("theses.detail.firstRevision")
                      : t("theses.detail.noChangeNote"))}
                </p>
                {r.review && (
                  <div className="mt-2">
                    <ReviewBriefLine brief={r.review} />
                  </div>
                )}
              </li>
            ))}
          </ol>
        </TabsContent>
        <TabsContent value="compare">
          <Compare thesis={th} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

const FROM_ID = "from";
const TO_ID = "to";

function Compare({ thesis }: { thesis: Thesis }) {
  const { t } = useTranslation();
  const numbers = thesis.revisions.map((r) => r.revision_no);
  const [from, setFrom] = useState(numbers.at(-2) ?? 1);
  const [to, setTo] = useState(numbers.at(-1) ?? 1);
  const diff = useRevisionDiff(thesis.id, from, to);
  const select = (id: string, value: number, set: (v: number) => void) => (
    <NativeSelect
      id={id}
      className="w-auto"
      value={value}
      onChange={(e) => set(Number(e.target.value))}
    >
      {numbers.map((n) => (
        <option key={n} value={n}>
          {n}
        </option>
      ))}
    </NativeSelect>
  );
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor={FROM_ID}>{t("theses.detail.fromRevision")}</Label>
        {select(FROM_ID, from, setFrom)}
        <Label htmlFor={TO_ID}>{t("theses.detail.toRevision")}</Label>
        {select(TO_ID, to, setTo)}
      </div>
      {diff.data && <DiffView diff={diff.data.unified_diff} />}
    </div>
  );
}

function Actions({
  thesis,
  onImported,
}: {
  thesis: Thesis;
  onImported: (revisionNo: number) => void;
}) {
  const { t } = useTranslation();
  const visibility = useSetVisibility(thesis.id);
  const copy = useCopyThesis(thesis.id);
  const drafts = useThesisDraft(thesis.id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const [importing, setImporting] = useState(false);
  const [activating, setActivating] = useState(false);
  const editDraft = () =>
    navigate({ to: "/theses/$thesisId/edit", params: { thesisId: String(thesis.id) } });

  if (!thesis.is_own) {
    return (
      <div className="grid gap-2">
        <Button
          variant="outline"
          onClick={() =>
            copy.mutate(undefined, {
              onSuccess: (c) =>
                navigate({ to: "/theses/$thesisId", params: { thesisId: String(c.id) } }),
            })
          }
        >
          {t("theses.detail.copy")}
        </Button>
        <FormError error={copy.error} />
      </div>
    );
  }
  const shared = thesis.visibility === "shared";
  const draft = thesis.revisions.find((r) => r.is_draft);
  return (
    <div className="grid justify-items-end gap-2">
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => visibility.mutate(shared ? "private" : "shared")}>
          {shared ? t("theses.detail.makePrivate") : t("theses.detail.share")}
        </Button>
        <Button variant="outline" onClick={() => setImporting(true)}>
          {t("theses.detail.import")}
        </Button>
        {draft ? (
          <>
            <Button
              variant="outline"
              onClick={() => drafts.remove.mutate()}
              disabled={draft.revision_no === 1}
              title={draft.revision_no === 1 ? t("theses.detail.firstCannotDelete") : undefined}
            >
              {t("theses.detail.deleteDraft")}
            </Button>
            <Button variant="outline" asChild>
              <Link to="/theses/$thesisId/edit" params={{ thesisId: String(thesis.id) }}>
                {t("theses.detail.editDraft")}
              </Link>
            </Button>
            <Button onClick={() => setActivating(true)}>{t("theses.detail.activateDraft")}</Button>
          </>
        ) : (
          <Button onClick={() => drafts.create.mutate(undefined, { onSuccess: editDraft })}>
            {t("theses.detail.newDraft")}
          </Button>
        )}
      </div>
      <FormError error={visibility.error ?? drafts.create.error ?? drafts.remove.error} />
      {activating && draft && (
        <ActivateDialog
          thesisId={thesis.id}
          revisionNo={draft.revision_no}
          savedNote={draft.change_note}
          warning={activationWarning(draft.review)}
          onClose={() => setActivating(false)}
        />
      )}
      {importing && (
        <FileImport
          title={t("theses.detail.importTitle")}
          description={
            draft
              ? t("theses.detail.importReplaces", { no: draft.revision_no })
              : t("theses.detail.importCreates")
          }
          preview={(text) => thesisImport.preview(text, thesis.id)}
          run={(text) => thesisImport.run(text, thesis.id)}
          renderPreview={(p) => (
            <p>
              <Trans
                i18nKey="theses.detail.importPreview"
                values={{ no: p.revision_no, title: p.title, status: statusLabel(p.status) }}
                components={{ strong: <strong /> }}
              />
            </p>
          )}
          onClose={() => setImporting(false)}
          onDone={(revision) => {
            setImporting(false);
            client.invalidateQueries({ queryKey: thesesKey });
            onImported(revision.revision_no);
          }}
        />
      )}
    </div>
  );
}

/** THS-02, THS-03: the draft becomes an immutable revision; from revision 2 on with a
 * change note. */
function ActivateDialog({
  thesisId,
  revisionNo,
  savedNote,
  warning,
  onClose,
}: {
  thesisId: number;
  revisionNo: number;
  savedNote: string | null;
  warning: string | null; // REV-11: no current review
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { activate } = useThesisDraft(thesisId);
  const [note, setNote] = useState(savedNote ?? "");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    activate.mutate(note.trim() || null, { onSuccess: onClose });
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{t("theses.detail.activateTitle", { no: revisionNo })}</DialogTitle>
        <DialogDescription>{t("theses.detail.activateDescription")}</DialogDescription>
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          {warning && <Alert variant="warning">{warning}</Alert>}
          <Field
            id="activation-note"
            label={
              revisionNo > 1 ? t("theses.detail.changeNote") : t("theses.detail.changeNoteFirst")
            }
            error={fieldError(activate.error, "change_note")}
          >
            <Input
              id="activation-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              required={revisionNo > 1}
            />
          </Field>
          <FormError error={activate.error} fields={["change_note"]} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={activate.isPending}>
              {warning ? t("theses.detail.activateAnyway") : t("theses.detail.activate")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
