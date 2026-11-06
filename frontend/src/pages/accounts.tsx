import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import i18n from "i18next";
import { useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";
import { ME_KEY, useMe } from "@/auth/auth";
import { Field, FormError, fieldError } from "@/components/form";
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
import { formatDate } from "@/lib/format";

type Account = components["schemas"]["Account"];

const ACCOUNTS = ["admin", "accounts"] as const;

/** USR-09: one or both roles. */
export function roleNames(account: { is_admin: boolean; is_investor: boolean }): string {
  return [
    account.is_admin && i18n.t("pages.accounts.roleAdmin"),
    account.is_investor && i18n.t("pages.accounts.roleInvestor"),
  ]
    .filter(Boolean)
    .join(", ");
}

function useAccountAction<T>(action: (body: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSuccess: () => client.invalidateQueries({ queryKey: ACCOUNTS }),
  });
}

/** USR-02, USR-06, USR-09: account management for admins. */
export function AccountsPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const accounts = useQuery({
    queryKey: ACCOUNTS,
    queryFn: () => unwrap(api.GET("/api/admin/accounts")),
  });
  const [dialog, setDialog] = useState<
    | { kind: "create" }
    | { kind: "reset" | "currency" | "delete" | "roles"; account: Account }
    | null
  >(null);
  const close = () => setDialog(null);

  const status = useAccountAction(({ id, active }: { id: number; active: boolean }) =>
    unwrap(
      active
        ? api.POST("/api/admin/accounts/{account_id}/reactivate", {
            params: { path: { account_id: id } },
          })
        : api.POST("/api/admin/accounts/{account_id}/deactivate", {
            params: { path: { account_id: id } },
          }),
    ),
  );

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t("pages.accounts.title")}</h1>
        <Button onClick={() => setDialog({ kind: "create" })}>
          {t("pages.accounts.newAccount")}
        </Button>
      </div>
      <FormError error={accounts.error ?? status.error} />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("pages.accounts.username")}</TableHead>
            <TableHead>{t("pages.accounts.role")}</TableHead>
            <TableHead>{t("pages.accounts.currency")}</TableHead>
            <TableHead>{t("pages.accounts.status")}</TableHead>
            <TableHead>{t("pages.accounts.created")}</TableHead>
            <TableHead className="text-right">{t("pages.accounts.actions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {accounts.data?.map((account) => (
            <TableRow key={account.id}>
              <TableCell className="font-medium">{account.username}</TableCell>
              <TableCell>{roleNames(account)}</TableCell>
              <TableCell>{account.base_currency ?? "–"}</TableCell>
              <TableCell>
                {account.active ? (
                  <Badge variant="success">{t("pages.accounts.active")}</Badge>
                ) : (
                  <Badge variant="secondary">{t("pages.accounts.deactivated")}</Badge>
                )}{" "}
                {account.must_change_password && (
                  <Badge variant="warning">{t("pages.accounts.temporaryPassword")}</Badge>
                )}
              </TableCell>
              <TableCell>{formatDate(account.created_at)}</TableCell>
              <TableCell className="text-right">
                <div className="flex flex-wrap justify-end gap-1">
                  {/* Also on the own account: an admin can become an investor too */}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setDialog({ kind: "roles", account })}
                  >
                    {t("pages.accounts.roles")}
                  </Button>
                  {account.is_investor && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setDialog({ kind: "currency", account })}
                    >
                      {t("pages.accounts.currencyButton")}
                    </Button>
                  )}
                  {account.id !== me?.id && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => status.mutate({ id: account.id, active: !account.active })}
                      >
                        {account.active
                          ? t("pages.accounts.deactivate")
                          : t("pages.accounts.reactivate")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDialog({ kind: "reset", account })}
                      >
                        {t("pages.accounts.resetPassword")}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => setDialog({ kind: "delete", account })}
                      >
                        {t("pages.accounts.delete")}
                      </Button>
                    </>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {dialog?.kind === "create" && <CreateDialog onClose={close} />}
      {dialog?.kind === "reset" && <ResetDialog account={dialog.account} onClose={close} />}
      {dialog?.kind === "currency" && <CurrencyDialog account={dialog.account} onClose={close} />}
      {dialog?.kind === "delete" && <DeleteDialog account={dialog.account} onClose={close} />}
      {dialog?.kind === "roles" && (
        <RolesDialog
          account={dialog.account}
          isSelf={dialog.account.id === me?.id}
          onClose={close}
        />
      )}
    </div>
  );
}

function FormDialog({
  title,
  description,
  onClose,
  onSubmit,
  error,
  fields,
  submitLabel,
  destructive,
  pending,
  children,
}: {
  title: string;
  description?: string;
  onClose: () => void;
  onSubmit: () => void;
  error: unknown;
  fields: string[];
  submitLabel: string;
  destructive?: boolean;
  pending: boolean;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        {description && <DialogDescription>{description}</DialogDescription>}
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          {children}
          <FormError error={error} fields={fields} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              type="submit"
              variant={destructive ? "destructive" : "default"}
              disabled={pending}
            >
              {submitLabel}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CreateDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isInvestor, setIsInvestor] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [currency, setCurrency] = useState("CHF");
  const create = useAccountAction(() =>
    unwrap(
      api.POST("/api/admin/accounts", {
        body: {
          username,
          temporary_password: password,
          is_admin: isAdmin,
          is_investor: isInvestor,
          ...(isInvestor && { base_currency: currency }),
        },
      }),
    ),
  );
  return (
    <FormDialog
      title={t("pages.accounts.newAccount")}
      description={t("pages.accounts.create.description")}
      onClose={onClose}
      onSubmit={() => create.mutate(undefined, { onSuccess: onClose })}
      error={create.error}
      fields={["username", "password", "roles", "base_currency"]}
      submitLabel={t("pages.accounts.create.submit")}
      pending={create.isPending}
    >
      <Field
        id="new-username"
        label={t("pages.accounts.username")}
        error={fieldError(create.error, "username")}
      >
        <Input
          id="new-username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </Field>
      <Field
        id="new-password"
        label={t("pages.accounts.create.temporaryPassword")}
        error={fieldError(create.error, "password")}
      >
        <Input
          id="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>
      <RoleChoice
        isAdmin={isAdmin}
        isInvestor={isInvestor}
        onAdmin={setIsAdmin}
        onInvestor={setIsInvestor}
        error={fieldError(create.error, "roles")}
      />
      {isInvestor && (
        <Field
          id="new-currency"
          label={t("pages.accounts.create.baseCurrency")}
          error={fieldError(create.error, "base_currency")}
        >
          <Input
            id="new-currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            maxLength={3}
            required
          />
        </Field>
      )}
    </FormDialog>
  );
}

/** USR-09: admin (accounts and AI reviewers) and investor (own investment data). */
function RoleChoice({
  isAdmin,
  isInvestor,
  onAdmin,
  onInvestor,
  error,
}: {
  isAdmin: boolean;
  isInvestor: boolean;
  onAdmin: (value: boolean) => void;
  onInvestor: (value: boolean) => void;
  error?: string;
}) {
  const { t } = useTranslation();
  return (
    <fieldset className="grid gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">
        {t("pages.accounts.roleChoice.legend")}
      </legend>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={isInvestor}
          onChange={(e) => onInvestor(e.target.checked)}
        />
        {t("pages.accounts.roleChoice.investor")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={isAdmin} onChange={(e) => onAdmin(e.target.checked)} />
        {t("pages.accounts.roleChoice.admin")}
      </label>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </fieldset>
  );
}

function RolesDialog({
  account,
  isSelf,
  onClose,
}: {
  account: Account;
  isSelf: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [isAdmin, setIsAdmin] = useState(account.is_admin);
  const [isInvestor, setIsInvestor] = useState(account.is_investor);
  const [currency, setCurrency] = useState("CHF");
  const addsInvestor = isInvestor && !account.is_investor;
  const change = useAccountAction(() =>
    unwrap(
      api.PUT("/api/admin/accounts/{account_id}/roles", {
        params: { path: { account_id: account.id } },
        body: {
          is_admin: isAdmin,
          is_investor: isInvestor,
          ...(addsInvestor && { base_currency: currency }),
        },
      }),
    ),
  );
  const done = () => {
    // The own roles decide the navigation
    if (isSelf) void client.invalidateQueries({ queryKey: ME_KEY });
    onClose();
  };
  return (
    <FormDialog
      title={t("pages.accounts.rolesDialog.title", { name: account.username })}
      description={t("pages.accounts.rolesDialog.description")}
      onClose={onClose}
      onSubmit={() => change.mutate(undefined, { onSuccess: done })}
      error={change.error}
      fields={["roles", "base_currency"]}
      submitLabel={t("common.save")}
      pending={change.isPending}
    >
      <RoleChoice
        isAdmin={isAdmin}
        isInvestor={isInvestor}
        onAdmin={setIsAdmin}
        onInvestor={setIsInvestor}
        error={fieldError(change.error, "roles")}
      />
      {addsInvestor && (
        <Field
          id="roles-currency"
          label={t("pages.accounts.create.baseCurrency")}
          error={fieldError(change.error, "base_currency")}
        >
          <Input
            id="roles-currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            maxLength={3}
            required
          />
        </Field>
      )}
    </FormDialog>
  );
}

function ResetDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const reset = useAccountAction(() =>
    unwrap(
      api.POST("/api/admin/accounts/{account_id}/reset-password", {
        params: { path: { account_id: account.id } },
        body: { temporary_password: password },
      }),
    ),
  );
  return (
    <FormDialog
      title={t("pages.accounts.resetDialog.title", { name: account.username })}
      description={t("pages.accounts.resetDialog.description")}
      onClose={onClose}
      onSubmit={() => reset.mutate(undefined, { onSuccess: onClose })}
      error={reset.error}
      fields={["temporary_password"]}
      submitLabel={t("pages.accounts.resetPassword")}
      pending={reset.isPending}
    >
      <Field
        id="temp-password"
        label={t("pages.accounts.create.temporaryPassword")}
        error={fieldError(reset.error, "temporary_password")}
      >
        <Input
          id="temp-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </Field>
    </FormDialog>
  );
}

function CurrencyDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const { t } = useTranslation();
  const [currency, setCurrency] = useState(account.base_currency ?? "");
  const change = useAccountAction(() =>
    unwrap(
      api.PUT("/api/admin/accounts/{account_id}/base-currency", {
        params: { path: { account_id: account.id } },
        body: { base_currency: currency },
      }),
    ),
  );
  return (
    <FormDialog
      title={t("pages.accounts.currencyDialog.title", { name: account.username })}
      description={t("pages.accounts.currencyDialog.description")}
      onClose={onClose}
      onSubmit={() => change.mutate(undefined, { onSuccess: onClose })}
      error={change.error}
      fields={["base_currency"]}
      submitLabel={t("common.save")}
      pending={change.isPending}
    >
      <Field
        id="currency"
        label={t("pages.accounts.create.baseCurrency")}
        error={fieldError(change.error, "base_currency")}
      >
        <Input
          id="currency"
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
          maxLength={3}
          required
        />
      </Field>
    </FormDialog>
  );
}

function DeleteDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const { t } = useTranslation();
  const [confirmation, setConfirmation] = useState("");
  const remove = useAccountAction(() =>
    unwrap(
      api.DELETE("/api/admin/accounts/{account_id}", {
        params: { path: { account_id: account.id } },
      }),
    ),
  );
  return (
    <FormDialog
      title={t("pages.accounts.deleteDialog.title", { name: account.username })}
      description={t("pages.accounts.deleteDialog.description")}
      onClose={onClose}
      onSubmit={() =>
        confirmation === account.username && remove.mutate(undefined, { onSuccess: onClose })
      }
      error={remove.error}
      fields={[]}
      submitLabel={t("pages.accounts.deleteDialog.submit")}
      destructive
      pending={remove.isPending || confirmation !== account.username}
    >
      <Field
        id="confirm-delete"
        label={t("pages.accounts.deleteDialog.confirm", { name: account.username })}
      >
        <Input
          id="confirm-delete"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
        />
      </Field>
    </FormDialog>
  );
}
