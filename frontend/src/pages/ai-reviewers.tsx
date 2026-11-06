import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, translateMessage, unwrap } from "@/api/client";
import type { components } from "@/api/schema";
import { Field, FormError, fieldError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { formatDateTime } from "@/lib/format";

type Reviewer = components["schemas"]["AiReviewerSettings"];

const REVIEWERS_KEY = ["admin", "ai-reviewers"] as const;

export const PROVIDERS = [
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "openai", label: "OpenAI" },
  { value: "google", label: "Google (Gemini)" },
];

const FIELDS = ["name", "description", "provider", "model", "api_key", "monthly_review_limit"];

/** REV-13 to REV-15: any number of AI reviewers, each with its LLM access and limit. */
export function AiReviewersPage() {
  const { t } = useTranslation();
  const reviewers = useQuery({
    queryKey: REVIEWERS_KEY,
    queryFn: () => unwrap(api.GET("/api/admin/ai-reviewers")),
  });
  const [adding, setAdding] = useState(false);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle
          title={t("pages.aiReviewers.title")}
          description={t("pages.aiReviewers.description")}
        />
        <Button onClick={() => setAdding(true)} disabled={adding}>
          {t("pages.aiReviewers.new")}
        </Button>
      </div>
      {/* NFR-01: what the reviews send to the provider */}
      <p className="max-w-prose text-sm text-muted-foreground">{t("pages.aiReviewers.dataNote")}</p>
      <FormError error={reviewers.error} />
      {reviewers.data && !reviewers.data.keys_available && (
        <Alert variant="warning">{t("pages.aiReviewers.noSecret")}</Alert>
      )}
      {reviewers.data?.reviewers.length === 0 && !adding && (
        <p className="text-sm text-muted-foreground">{t("pages.aiReviewers.none")}</p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {adding && <ReviewerCard onDone={() => setAdding(false)} />}
        {reviewers.data?.reviewers.map((reviewer) => (
          <ReviewerCard key={reviewer.id} reviewer={reviewer} />
        ))}
      </div>
    </div>
  );
}

/** A new reviewer without `reviewer`; `onDone` closes it after creating or cancelling. */
function ReviewerCard({ reviewer, onDone }: { reviewer?: Reviewer; onDone?: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [name, setName] = useState(reviewer?.name ?? "");
  const [description, setDescription] = useState(reviewer?.description ?? "");
  const [provider, setProvider] = useState(reviewer?.provider ?? "anthropic");
  const [model, setModel] = useState(reviewer?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [limit, setLimit] = useState(String(reviewer?.monthly_review_limit ?? 10));
  const [enabled, setEnabled] = useState(reviewer?.enabled ?? true);
  const [archiving, setArchiving] = useState(false);

  const body = () => ({
    name,
    description: description || null,
    provider,
    model,
    monthly_review_limit: Number(limit),
    enabled,
    api_key: apiKey || null,
  });
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        reviewer
          ? api.PUT("/api/admin/ai-reviewers/{reviewer_id}", {
              params: { path: { reviewer_id: reviewer.id } },
              body: body(),
            })
          : api.POST("/api/admin/ai-reviewers", { body: body() }),
      ),
    onSuccess: async () => {
      setApiKey("");
      await client.invalidateQueries({ queryKey: REVIEWERS_KEY });
      onDone?.();
    },
  });
  const test = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST("/api/admin/ai-reviewers/{reviewer_id}/test", {
          params: { path: { reviewer_id: id } },
        }),
      ),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    test.reset();
    save.mutate();
  };
  const id = (field: string) => `${reviewer?.id ?? "new"}-${field}`;
  const title = reviewer ? reviewer.name : t("pages.aiReviewers.new");

  return (
    <Card>
      <CardContent className="pt-5">
        <form
          className="grid gap-4"
          onSubmit={submit}
          aria-label={t("pages.aiReviewers.form", { name: title })}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold">
              {title}{" "}
              {reviewer && !reviewer.enabled && (
                <Badge variant="secondary">{t("pages.aiReviewers.disabled")}</Badge>
              )}
            </h2>
            {reviewer && (
              <span className="text-sm text-muted-foreground">
                {t("pages.aiReviewers.changed", { date: formatDateTime(reviewer.updated_at) })}
              </span>
            )}
          </div>
          <Field
            id={id("name")}
            label={t("pages.aiReviewers.name")}
            error={fieldError(save.error, "name")}
          >
            <Input
              id={id("name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </Field>
          <Field
            id={id("description")}
            label={t("pages.aiReviewers.descriptionLabel")}
            error={fieldError(save.error, "description")}
          >
            <Input
              id={id("description")}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("pages.aiReviewers.descriptionPlaceholder")}
            />
          </Field>
          <Field
            id={id("provider")}
            label={t("pages.aiReviewers.provider")}
            error={fieldError(save.error, "provider")}
          >
            <NativeSelect
              id={id("provider")}
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field
            id={id("model")}
            label={t("pages.aiReviewers.model")}
            error={fieldError(save.error, "model")}
          >
            <Input
              id={id("model")}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={t("pages.aiReviewers.modelPlaceholder")}
              required
            />
          </Field>
          <Field
            id={id("key")}
            label={t("pages.aiReviewers.apiKey")}
            error={fieldError(save.error, "api_key")}
          >
            <Input
              id={id("key")}
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                reviewer
                  ? t("pages.aiReviewers.keyStored", { last4: reviewer.api_key_last4 })
                  : t("pages.aiReviewers.keyNew")
              }
              required={!reviewer}
            />
          </Field>
          <Field
            id={id("limit")}
            label={t("pages.aiReviewers.limit")}
            error={fieldError(save.error, "monthly_review_limit")}
          >
            <Input
              id={id("limit")}
              type="number"
              min={0}
              step={1}
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              required
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            {t("pages.aiReviewers.enabled")}
          </label>
          <FormError error={save.error} fields={FIELDS} />
          {test.data && (
            <Alert variant={test.data.ok ? "default" : "destructive"}>
              {translateMessage(test.data.code, test.data.params, test.data.message)}
            </Alert>
          )}
          <FormError error={test.error} />
          <div className="flex flex-wrap justify-end gap-2">
            {reviewer ? (
              <>
                <Button type="button" variant="outline" onClick={() => setArchiving(true)}>
                  {t("pages.aiReviewers.archive")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => test.mutate(reviewer.id)}
                  disabled={test.isPending}
                >
                  {test.isPending ? t("pages.aiReviewers.testing") : t("pages.aiReviewers.test")}
                </Button>
              </>
            ) : (
              <Button type="button" variant="outline" onClick={onDone}>
                {t("common.cancel")}
              </Button>
            )}
            <Button type="submit" disabled={save.isPending}>
              {reviewer ? t("common.save") : t("pages.aiReviewers.create")}
            </Button>
          </div>
        </form>
      </CardContent>
      {archiving && reviewer && (
        <ArchiveDialog reviewer={reviewer} onClose={() => setArchiving(false)} />
      )}
    </Card>
  );
}

function ArchiveDialog({ reviewer, onClose }: { reviewer: Reviewer; onClose: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const archive = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/admin/ai-reviewers/{reviewer_id}/archive", {
          params: { path: { reviewer_id: reviewer.id } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: REVIEWERS_KEY }),
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>
          {t("pages.aiReviewers.archiveDialog.title", { name: reviewer.name })}
        </DialogTitle>
        <DialogDescription>{t("pages.aiReviewers.archiveDialog.description")}</DialogDescription>
        <FormError error={archive.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={archive.isPending}
            onClick={() => archive.mutate(undefined, { onSuccess: onClose })}
          >
            {t("pages.aiReviewers.archive")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
