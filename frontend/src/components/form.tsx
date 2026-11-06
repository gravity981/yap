import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { Alert } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";

/** Label, control, an optional hint and the server's message for this field (IMP-06 paths). */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && (
        <p className="text-xs text-muted-foreground" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="text-xs text-destructive" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}

export function fieldError(error: unknown, path: string): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  return error.problems.find((p) => p.path === path)?.message;
}

/** Errors that do not belong to a single field. */
export function FormError({ error, fields = [] }: { error: unknown; fields?: string[] }) {
  const { t } = useTranslation();
  if (!error) return null;
  if (error instanceof ApiError) {
    const other = error.problems.filter((p) => !fields.includes(p.path));
    if (error.problems.length > 0 && other.length === 0) return null;
    return (
      <Alert variant="destructive">
        {other.length > 0
          ? other.map((p) => <div key={p.path + p.message}>{p.message}</div>)
          : error.message}
      </Alert>
    );
  }
  return <Alert variant="destructive">{t("components.form.unexpected")}</Alert>;
}
