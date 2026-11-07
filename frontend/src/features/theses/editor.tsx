import { Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Field, FormError, fieldError } from "@/components/form";
import { MarkdownEditor } from "@/components/lazy-markdown-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { ReviewPane } from "@/features/reviews/pane";

import type { ReviewBrief } from "@/features/reviews/api";

import { useCreateThesis, useRevision, useThesis, useThesisDraft } from "./api";
import { statusLabel, THESIS_STATUSES } from "./status";
import { thesisTemplate } from "./template";

const FIELDS = ["title", "content_md", "status", "change_note", "visibility"];

/** New thesis, starting from the template (THS-07); it starts as a draft (THS-02). */
export function NewThesisPage() {
  const { t } = useTranslation();
  const create = useCreateThesis();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState(thesisTemplate);
  const [visibility, setVisibility] = useState("private");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { title, content_md: content, visibility },
      {
        onSuccess: (created) =>
          navigate({ to: "/theses/$thesisId", params: { thesisId: String(created.id) } }),
      },
    );
  };

  return (
    <form className="grid gap-4" onSubmit={submit}>
      <h1 className="text-2xl font-semibold">{t("theses.editor.newTitle")}</h1>
      <p className="text-sm text-muted-foreground">{t("theses.editor.newHint")}</p>
      <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
        <Field
          id="title"
          label={t("theses.editor.title")}
          error={fieldError(create.error, "title")}
        >
          <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field id="visibility" label={t("theses.editor.visibility")}>
          <NativeSelect
            id="visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
          >
            <option value="private">{t("theses.visibility.private")}</option>
            <option value="shared">{t("theses.visibility.shared")}</option>
          </NativeSelect>
        </Field>
      </div>
      <MarkdownEditor value={content} onChange={setContent} />
      <FormError error={create.error} fields={FIELDS} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => navigate({ to: "/theses" })}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {t("theses.editor.create")}
        </Button>
      </div>
    </form>
  );
}

/** Edits the draft; it becomes a revision only when activated (THS-02 to THS-04). */
export function EditThesisPage({ thesisId }: { thesisId: number }) {
  const { t } = useTranslation();
  const thesis = useThesis(thesisId);
  const draft = thesis.data?.revisions.find((r) => r.is_draft);
  const revision = useRevision(thesisId, draft?.revision_no);
  if (thesis.data && !draft) {
    return (
      <p className="text-muted-foreground">
        {t("theses.editor.noDraft")}{" "}
        <Link to="/theses/$thesisId" params={{ thesisId: String(thesisId) }} className="underline">
          {t("theses.editor.createOnPage")}
        </Link>
      </p>
    );
  }
  if (!revision.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  return <DraftForm thesisId={thesisId} initial={revision.data} brief={draft?.review} />;
}

function DraftForm({
  thesisId,
  initial,
  brief,
}: {
  thesisId: number;
  brief: ReviewBrief | null | undefined;
  initial: {
    title: string;
    content_md: string;
    status: string;
    revision_no: number;
    change_note: string | null;
  };
}) {
  const { t } = useTranslation();
  const { save } = useThesisDraft(thesisId);
  const navigate = useNavigate();
  const [title, setTitle] = useState(initial.title);
  const [content, setContent] = useState(initial.content_md);
  const [status, setStatus] = useState(initial.status);
  const [note, setNote] = useState(initial.change_note ?? "");
  const back = () => navigate({ to: "/theses/$thesisId", params: { thesisId: String(thesisId) } });

  const body = () => ({ title, content_md: content, status, change_note: note.trim() || null });
  const submit = () => save.mutate(body(), { onSuccess: back });

  // Not a <form>: the review pane in the editor has forms of its own (REV-18)
  return (
    <div className="grid gap-4">
      <h1 className="text-2xl font-semibold">
        {t("theses.editor.editTitle", { no: initial.revision_no })}
      </h1>
      <p className="text-sm text-muted-foreground">
        {t("theses.editor.editHint", { no: initial.revision_no })}
      </p>
      <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
        <Field id="title" label={t("theses.editor.title")} error={fieldError(save.error, "title")}>
          <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field
          id="status"
          label={t("theses.editor.status")}
          error={fieldError(save.error, "status")}
        >
          <NativeSelect id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
            {THESIS_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      {status !== "intact" && status !== initial.status && (
        <p className="text-sm text-muted-foreground">{t("theses.editor.statusHint")}</p>
      )}
      <MarkdownEditor
        value={content}
        onChange={setContent}
        aside={{
          label: t("reviews.pane.tab"),
          // REV-01: a review saves the draft first, so it sees what is in the editor
          content: (
            <ReviewPane
              kind="thesis"
              ownerId={thesisId}
              brief={brief}
              save={() => save.mutateAsync(body())}
            />
          ),
        }}
      />
      {initial.revision_no > 1 && (
        <Field
          id="change-note"
          label={t("theses.editor.changeNote")}
          error={fieldError(save.error, "change_note")}
        >
          <Input
            id="change-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t("theses.editor.changeNotePlaceholder")}
          />
        </Field>
      )}
      <FormError error={save.error} fields={FIELDS} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={back}>
          {t("common.cancel")}
        </Button>
        <Button type="button" onClick={submit} disabled={save.isPending}>
          {t("theses.editor.saveDraft")}
        </Button>
      </div>
    </div>
  );
}
