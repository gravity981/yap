import { useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { useChangePassword, useMe } from "@/auth/auth";
import { Field, FormError, fieldError } from "@/components/form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export const MIN_PASSWORD_LENGTH = 12;

/** USR-03; also the forced change after a reset or a new account (USR-02). */
export function ChangePasswordPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const change = useChangePassword();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    if (next.length < MIN_PASSWORD_LENGTH) {
      setLocalError(t("pages.password.tooShort", { min: MIN_PASSWORD_LENGTH }));
      return;
    }
    if (next !== repeat) {
      setLocalError(t("pages.password.mismatch"));
      return;
    }
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setDone(true);
          setCurrent("");
          setNext("");
          setRepeat("");
          if (me?.must_change_password) navigate({ to: "/" });
        },
      },
    );
  };

  return (
    <div className="mx-auto w-full max-w-md p-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("pages.password.title")}</CardTitle>
          {me?.must_change_password && (
            <CardDescription>{t("pages.password.temporary")}</CardDescription>
          )}
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <Field
              id="current"
              label={t("pages.password.current")}
              error={fieldError(change.error, "current_password")}
            >
              <Input
                id="current"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </Field>
            <Field
              id="new"
              label={t("pages.password.new")}
              error={fieldError(change.error, "new_password")}
            >
              <Input
                id="new"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </Field>
            <Field id="repeat" label={t("pages.password.repeat")}>
              <Input
                id="repeat"
                type="password"
                autoComplete="new-password"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                required
              />
            </Field>
            {localError && <Alert variant="destructive">{localError}</Alert>}
            <FormError error={change.error} fields={["current_password", "new_password"]} />
            {done && <Alert>{t("pages.password.changed")}</Alert>}
            <Button type="submit" disabled={change.isPending}>
              {t("pages.password.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
