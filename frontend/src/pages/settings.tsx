import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, unwrap } from "@/api/client";
import { ME_KEY, useMe, useSetLanguage, useSetTimeZone } from "@/auth/auth";
import { Field, FormError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/select";
import { PriceSourcesCard } from "@/features/prices/price-sources-card";
import { usageKey, useReviewerOptions, useUsage } from "@/features/reviews/api";
import { LANGUAGES } from "@/i18n";
import { browserTimeZone, timeZones } from "@/lib/format";

/** The own settings: language and time zone for every account (USR-10, USR-11), the
 * default AI reviewer and the price sources for investors (USR-08, PRC-05). */
export function SettingsPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  return (
    <div className="grid max-w-3xl gap-4">
      <PageTitle title={t("settings.title")} description={t("settings.description")} />
      <LanguageCard />
      <TimeZoneCard />
      {me?.is_investor && <ReviewerCard />}
      {me?.is_investor && <PriceSourcesCard />}
    </div>
  );
}

function LanguageCard() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const change = useSetLanguage();
  return (
    <Card>
      <CardContent className="grid gap-4 pt-5">
        <div className="grid gap-1">
          <h2 className="text-lg font-semibold">{t("settings.language.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("settings.language.description")}</p>
        </div>
        <Field id="language" label={t("settings.language.label")}>
          {/* Saved right away; the app switches as soon as the account is updated */}
          <NativeSelect
            id="language"
            className="w-auto"
            value={me?.language ?? ""}
            disabled={change.isPending}
            onChange={(e) => change.mutate(e.target.value || null)}
          >
            <option value="">{t("settings.language.browser")}</option>
            {LANGUAGES.map((language) => (
              <option key={language} value={language}>
                {t(`settings.language.${language}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <FormError error={change.error} />
      </CardContent>
    </Card>
  );
}

function TimeZoneCard() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const change = useSetTimeZone();
  const zones = timeZones();
  const current = me?.time_zone ?? "";
  return (
    <Card>
      <CardContent className="grid gap-4 pt-5">
        <div className="grid gap-1">
          <h2 className="text-lg font-semibold">{t("settings.timeZone.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("settings.timeZone.description")}</p>
        </div>
        <Field id="time-zone" label={t("settings.timeZone.label")}>
          {/* Saved right away, like the language */}
          <NativeSelect
            id="time-zone"
            className="w-auto"
            value={current}
            disabled={change.isPending}
            onChange={(e) => change.mutate(e.target.value || null)}
          >
            <option value="">{t("settings.timeZone.browser", { zone: browserTimeZone() })}</option>
            {/* A stored zone the browser does not list stays selectable */}
            {current && !zones.includes(current) && <option value={current}>{current}</option>}
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <FormError error={change.error} />
      </CardContent>
    </Card>
  );
}

function ReviewerCard() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { data: me } = useMe();
  const usage = useUsage();
  const options = useReviewerOptions();
  // USR-08: an AI reviewer's ID, "manual" (REV-18), or null for no choice yet
  type Method = number | "manual" | null;
  const [chosen, setChosen] = useState<Method | undefined>(undefined);
  const current: Method = me?.manual_review_default ? "manual" : (me?.ai_reviewer_id ?? null);
  const selected = chosen === undefined ? current : chosen;
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/ai-reviewers/choice", {
          body:
            selected === "manual"
              ? { ai_reviewer_id: null, manual: true }
              : { ai_reviewer_id: selected, manual: false },
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ME_KEY }),
        client.invalidateQueries({ queryKey: usageKey }),
      ]);
      setChosen(undefined); // the stored choice from now on
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const currentGone =
    typeof current === "number" && options.data && !options.data.some((o) => o.id === current);

  return (
    <Card>
      <CardContent className="pt-5">
        <form className="grid gap-4" onSubmit={submit} aria-label={t("settings.reviewer.title")}>
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">{t("settings.reviewer.title")}</h2>
            <p className="text-sm text-muted-foreground">{t("settings.reviewer.description")}</p>
          </div>
          {usage.data?.ai_reviewer_name && (
            <p className="text-sm">
              {t("settings.reviewer.usage", {
                used: usage.data.used,
                limit: usage.data.limit,
                name: usage.data.ai_reviewer_name,
              })}
            </p>
          )}
          {currentGone && <Alert variant="warning">{t("settings.reviewer.gone")}</Alert>}
          {options.data?.length === 0 && (
            <Alert variant="warning">{t("settings.reviewer.none")}</Alert>
          )}
          <fieldset className="grid gap-2">
            <legend className="sr-only">{t("settings.reviewer.title")}</legend>
            {options.data?.map((option) => (
              <label
                key={option.id}
                className="flex cursor-pointer items-start gap-3 rounded-md border p-3 has-[:checked]:border-primary"
              >
                <input
                  type="radio"
                  name="ai-reviewer"
                  className="mt-1"
                  checked={selected === option.id}
                  onChange={() => setChosen(option.id)}
                />
                <span className="grid gap-0.5">
                  <span className="font-medium">{option.name}</span>
                  {option.description && <span className="text-sm">{option.description}</span>}
                  <span className="text-xs text-muted-foreground">
                    {t("settings.reviewer.perMonth", {
                      provider: option.provider,
                      model: option.model,
                      limit: option.monthly_review_limit,
                    })}
                  </span>
                </span>
              </label>
            ))}
            <label className="flex cursor-pointer items-start gap-3 rounded-md border p-3 has-[:checked]:border-primary">
              <input
                type="radio"
                name="ai-reviewer"
                className="mt-1"
                checked={selected === "manual"}
                onChange={() => setChosen("manual")}
              />
              <span className="grid gap-0.5">
                <span className="font-medium">{t("settings.reviewer.manual")}</span>
                <span className="text-sm">{t("settings.reviewer.manualDescription")}</span>
              </span>
            </label>
          </fieldset>
          <FormError error={options.error ?? save.error} />
          {save.isSuccess && <Alert>{t("common.saved")}</Alert>}
          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={save.isPending || selected === null || selected === current}
            >
              {t("common.save")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
