import { Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Field, FormError, fieldError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useTheses } from "@/features/theses/api";

import { useCreatePolicy, usePolicies } from "./api";

/** POL-01, POL-12 */
export function PoliciesPage() {
  const { t } = useTranslation();
  const policies = usePolicies();
  const [creating, setCreating] = useState(false);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle title={t("policies.list.title")} description={t("policies.list.description")} />
        <Button onClick={() => setCreating(true)}>{t("policies.list.newPolicy")}</Button>
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
    </div>
  );
}

function NewPolicyDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const theses = useTheses();
  const create = useCreatePolicy();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [thesisId, setThesisId] = useState("");
  // POL-01: a policy can only use an activated thesis revision
  const usable = (theses.data ?? []).filter((th) => th.active_revision_no !== null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      { name, thesis_id: Number(thesisId) },
      {
        onSuccess: (p) =>
          navigate({ to: "/policies/$policyId", params: { policyId: String(p.id) } }),
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
          <Field id="policy-thesis" label={t("policies.create.thesis")}>
            <NativeSelect
              id="policy-thesis"
              value={thesisId}
              onChange={(e) => setThesisId(e.target.value)}
              required
            >
              <option value="" disabled>
                {t("policies.create.chooseThesis")}
              </option>
              {usable.map((th) => (
                <option key={th.id} value={th.id}>
                  {th.latest.title}
                  {th.is_own ? "" : t("policies.create.shared")}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {theses.data && usable.length < theses.data.length && (
            <p className="text-sm text-muted-foreground">{t("policies.create.draftsHidden")}</p>
          )}
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
