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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { thesisTemplate } from "@/features/theses/template";

import { policiesKey, thesisImport, useCreatePolicy, usePolicies } from "./api";

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
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("policies.list.policy")}</TableHead>
              <TableHead>{t("policies.list.activeVersion")}</TableHead>
              <TableHead>{t("policies.list.draft")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.data.map((p) => (
              <TableRow key={p.id}>
                <TableCell>
                  <Link
                    to="/policies/$policyId"
                    params={{ policyId: String(p.id) }}
                    className="font-medium hover:underline"
                  >
                    {p.name}
                  </Link>{" "}
                  {p.archived_at && (
                    <Badge variant="secondary">{t("policies.list.archived")}</Badge>
                  )}
                </TableCell>
                <TableCell>{p.active_version_label ?? t("policies.list.noneYet")}</TableCell>
                <TableCell>
                  {p.has_draft && <Badge variant="outline">{t("policies.list.draftBadge")}</Badge>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
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
