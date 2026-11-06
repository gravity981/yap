import { useNavigate } from "@tanstack/react-router";
import i18n from "i18next";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "@/api/client";
import { useLogin } from "@/auth/auth";
import { APP_NAME, RobotLogo } from "@/components/brand";
import { Field } from "@/components/form";
import { NotAdvice } from "@/components/disclaimer";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

function loginMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return i18n.t("pages.login.tooMany");
  }
  if (error instanceof ApiError && error.status === 401) return i18n.t("pages.login.invalid");
  return i18n.t("pages.login.failed");
}

/** USR-01 */
export function LoginPage() {
  const { t } = useTranslation();
  const login = useLogin();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ username, password }, { onSuccess: () => navigate({ to: "/" }) });
  };

  return (
    <main className="flex min-h-svh flex-col items-center justify-center p-4">
      <RobotLogo className="mb-6 max-w-xl" />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{APP_NAME}</CardTitle>
          <CardDescription>{t("pages.login.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <Field id="username" label={t("pages.login.username")}>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </Field>
            <Field id="password" label={t("pages.login.password")}>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            {login.isError && <Alert variant="destructive">{loginMessage(login.error)}</Alert>}
            <Button type="submit" disabled={login.isPending}>
              {login.isPending ? t("pages.login.pending") : t("pages.login.submit")}
            </Button>
          </form>
        </CardContent>
      </Card>
      <NotAdvice className="mt-4 max-w-sm text-center" />
    </main>
  );
}
