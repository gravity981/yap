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
import { formatDateTime, timeZones } from "@/lib/format";
import i18n from "i18next";

type Provider = components["schemas"]["PriceProviderSettings"];
type Addable = components["schemas"]["AddableProvider"];

const PROVIDERS_KEY = ["admin", "price-providers"] as const;
const FIELDS = ["provider", "api_key", "daily_call_limit"];
// PRC-01: Yahoo Finance is an unofficial interface
const UNOFFICIAL = "yahoo";

/** PRC-01, PRC-10, PRC-11: the price providers and the built-in exchange rate source. */
export function PriceProvidersPage() {
  const { t } = useTranslation();
  const providers = useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: () => unwrap(api.GET("/api/admin/price-providers")),
  });
  const [adding, setAdding] = useState<Addable | null>(null);
  const addable = providers.data?.addable ?? [];
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle
          title={t("pages.priceProviders.title")}
          description={t("pages.priceProviders.description")}
        />
        {addable.length > 0 && !adding && (
          <NativeSelect
            aria-label={t("pages.priceProviders.add")}
            className="w-auto"
            value=""
            onChange={(e) => setAdding(addable.find((a) => a.provider === e.target.value) ?? null)}
          >
            <option value="" disabled>
              {t("pages.priceProviders.add")}
            </option>
            {addable.map((a) => (
              <option key={a.provider} value={a.provider}>
                {a.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </div>
      {/* NFR-01: what the providers receive */}
      <p className="max-w-prose text-sm text-muted-foreground">
        {t("pages.priceProviders.dataNote")}
      </p>
      <FormError error={providers.error} />
      <ScheduleCard />
      {providers.data && !providers.data.keys_available && (
        <Alert variant="warning">{t("pages.aiReviewers.noSecret")}</Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {adding && (
          <ProviderCard key={adding.provider} adding={adding} onDone={() => setAdding(null)} />
        )}
        {providers.data?.providers.map((provider) =>
          provider.built_in ? (
            <BuiltInCard key={provider.id} provider={provider} />
          ) : (
            <ProviderCard key={provider.id} provider={provider} />
          ),
        )}
      </div>
    </div>
  );
}

function useConnectionTest() {
  return useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.POST("/api/admin/price-providers/{provider_id}/test", {
          params: { path: { provider_id: id } },
        }),
      ),
  });
}

function Calls({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-0.5 text-sm text-muted-foreground">
      <p>
        {provider.daily_call_limit === null
          ? t("pages.priceProviders.calls", { calls: provider.calls_today })
          : t("pages.priceProviders.callsOf", {
              calls: provider.calls_today,
              limit: provider.daily_call_limit,
            })}{" "}
        {provider.quota_exhausted && (
          <Badge variant="warning">{t("pages.priceProviders.quotaExhausted")}</Badge>
        )}
      </p>
      {/* PRC-10 */}
      {!provider.built_in && (
        <p>{t("pages.priceProviders.listingsInUse", { count: provider.listings_in_use })}</p>
      )}
      {provider.last_run && <p>{runText(provider.last_run)}</p>}
    </div>
  );
}

function runText(counts: Record<string, number>): string {
  return i18n.t("pages.priceProviders.runResult", {
    updated: counts.updated ?? 0,
    skipped: counts.skipped ?? 0,
    failed: (counts.failed ?? 0) + (counts.not_found ?? 0),
  });
}

const UPDATE_KEY = ["admin", "price-update"] as const;

/** PRC-07, PRC-10: when the price update runs, and how the last run went. The time of day
 * is read in the chosen time zone (NFR-14). */
function ScheduleCard() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const update = useQuery({
    queryKey: UPDATE_KEY,
    queryFn: () => unwrap(api.GET("/api/admin/price-update")),
  });
  const [form, setForm] = useState<{ time: string; zone: string; interval: string } | null>(null);
  const data = update.data;
  const current = form ?? {
    time: data?.time_of_day ?? "22:00",
    zone: data?.time_zone ?? "UTC",
    interval: String(data?.interval_hours ?? 24),
  };
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/admin/price-update", {
          body: {
            time_of_day: current.time,
            time_zone: current.zone,
            interval_hours: Number(current.interval),
          },
        }),
      ),
    onSuccess: (saved) => {
      client.setQueryData(UPDATE_KEY, saved);
      setForm(null);
    },
  });
  const zones = timeZones();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <Card>
      <CardContent className="pt-5">
        <form
          className="grid gap-4"
          onSubmit={submit}
          aria-label={t("pages.priceProviders.schedule.title")}
        >
          <div className="grid gap-1">
            <h2 className="text-lg font-semibold">{t("pages.priceProviders.schedule.title")}</h2>
            <p className="text-sm text-muted-foreground">
              {t("pages.priceProviders.schedule.description")}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <Field
              id="update-time"
              label={t("pages.priceProviders.schedule.time")}
              error={fieldError(save.error, "time_of_day")}
            >
              <Input
                id="update-time"
                type="time"
                className="w-32"
                value={current.time}
                onChange={(e) => setForm({ ...current, time: e.target.value })}
                required
              />
            </Field>
            <Field
              id="update-zone"
              label={t("pages.priceProviders.schedule.zone")}
              error={fieldError(save.error, "time_zone")}
            >
              <NativeSelect
                id="update-zone"
                className="w-auto"
                value={current.zone}
                onChange={(e) => setForm({ ...current, zone: e.target.value })}
              >
                {!zones.includes(current.zone) && (
                  <option value={current.zone}>{current.zone}</option>
                )}
                {zones.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field
              id="update-interval"
              label={t("pages.priceProviders.schedule.interval")}
              error={fieldError(save.error, "interval_hours")}
            >
              <NativeSelect
                id="update-interval"
                className="w-auto"
                value={current.interval}
                onChange={(e) => setForm({ ...current, interval: e.target.value })}
              >
                {(data?.intervals ?? [24]).map((hours) => (
                  <option key={hours} value={hours}>
                    {t("pages.priceProviders.schedule.every", { count: hours })}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Button type="submit" disabled={save.isPending || form === null}>
              {t("common.save")}
            </Button>
          </div>
          <FormError
            error={update.error ?? save.error}
            fields={["time_of_day", "time_zone", "interval_hours"]}
          />
          <div className="grid gap-0.5 text-sm">
            {data?.next_run_at && (
              <p>
                {t("pages.priceProviders.schedule.next", {
                  date: formatDateTime(data.next_run_at),
                })}
              </p>
            )}
            {data?.last_run ? (
              <>
                <p>
                  {t("pages.priceProviders.schedule.last", {
                    date: formatDateTime(data.last_run.started_at),
                    trigger: t(
                      data.last_run.trigger === "cli"
                        ? "pages.priceProviders.schedule.cli"
                        : "pages.priceProviders.schedule.scheduled",
                    ),
                  })}
                  {data.last_run.finished_at === null &&
                    ` ${t("pages.priceProviders.schedule.running")}`}
                </p>
                {Object.entries(data.last_run.result ?? {}).map(([name, counts]) => (
                  <p key={name} className="text-muted-foreground">
                    {name}: {runText(counts)}
                  </p>
                ))}
              </>
            ) : (
              <p className="text-muted-foreground">{t("pages.priceProviders.schedule.never")}</p>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function TestResult({ test }: { test: ReturnType<typeof useConnectionTest> }) {
  return (
    <>
      {test.data && (
        <Alert variant={test.data.ok ? "default" : "destructive"}>
          {translateMessage(test.data.code, test.data.params, test.data.message)}
        </Alert>
      )}
      <FormError error={test.error} />
    </>
  );
}

/** PRC-11: listed like the others, with a connection test, but not changeable. */
function BuiltInCard({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  const test = useConnectionTest();
  return (
    <Card>
      <CardContent className="grid gap-3 pt-5">
        <h2 className="text-lg font-semibold">
          {provider.name} <Badge variant="secondary">{t("pages.priceProviders.builtIn")}</Badge>
        </h2>
        <p className="text-sm">{t("pages.priceProviders.builtInDescription")}</p>
        <Calls provider={provider} />
        <TestResult test={test} />
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={() => test.mutate(provider.id)}
            disabled={test.isPending}
          >
            {test.isPending ? t("pages.aiReviewers.testing") : t("pages.aiReviewers.test")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/** A configured provider, or one being added (`adding`); `onDone` closes the new one. */
function ProviderCard({
  provider,
  adding,
  onDone,
}: {
  provider?: Provider;
  adding?: Addable;
  onDone?: () => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const kind = provider ?? adding!;
  const [apiKey, setApiKey] = useState("");
  const [limit, setLimit] = useState(
    provider?.daily_call_limit === null || provider === undefined
      ? ""
      : String(provider.daily_call_limit),
  );
  const [enabled, setEnabled] = useState(provider?.enabled ?? true);
  const [archiving, setArchiving] = useState(false);
  const test = useConnectionTest();

  const body = () => ({
    provider: kind.provider,
    daily_call_limit: limit === "" ? null : Number(limit),
    enabled,
    api_key: apiKey || null,
  });
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        provider
          ? api.PUT("/api/admin/price-providers/{provider_id}", {
              params: { path: { provider_id: provider.id } },
              body: body(),
            })
          : api.POST("/api/admin/price-providers", { body: body() }),
      ),
    onSuccess: async () => {
      setApiKey("");
      await client.invalidateQueries({ queryKey: PROVIDERS_KEY });
      onDone?.();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    test.reset();
    save.mutate();
  };
  const id = (field: string) => `${provider?.id ?? "new"}-${field}`;

  return (
    <Card>
      <CardContent className="pt-5">
        <form
          className="grid gap-4"
          onSubmit={submit}
          aria-label={t("pages.priceProviders.form", { name: kind.name })}
        >
          <h2 className="text-lg font-semibold">
            {kind.name}{" "}
            {provider && !provider.enabled && (
              <Badge variant="secondary">{t("pages.aiReviewers.disabled")}</Badge>
            )}
          </h2>
          {kind.provider === UNOFFICIAL && (
            <p className="text-sm text-muted-foreground">{t("pages.priceProviders.unofficial")}</p>
          )}
          {provider && <Calls provider={provider} />}
          {kind.key_possible && (
            <Field
              id={id("key")}
              label={
                kind.key_required
                  ? t("pages.aiReviewers.apiKey")
                  : t("pages.priceProviders.apiKeyOptional")
              }
              error={fieldError(save.error, "api_key")}
            >
              <Input
                id={id("key")}
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  provider?.api_key_last4
                    ? t("pages.aiReviewers.keyStored", { last4: provider.api_key_last4 })
                    : t("pages.aiReviewers.keyNew")
                }
                required={kind.key_required && !provider?.api_key_last4}
              />
            </Field>
          )}
          <Field
            id={id("limit")}
            label={t("pages.priceProviders.limit")}
            hint={t("pages.priceProviders.limitHint")}
            error={fieldError(save.error, "daily_call_limit")}
          >
            <Input
              id={id("limit")}
              type="number"
              min={0}
              step={1}
              className="w-32"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            {t("pages.priceProviders.enabled")}
          </label>
          <FormError error={save.error} fields={FIELDS} />
          <TestResult test={test} />
          <div className="flex flex-wrap justify-end gap-2">
            {provider ? (
              <>
                <Button type="button" variant="outline" onClick={() => setArchiving(true)}>
                  {t("pages.aiReviewers.archive")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => test.mutate(provider.id)}
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
              {provider ? t("common.save") : t("pages.priceProviders.create")}
            </Button>
          </div>
        </form>
      </CardContent>
      {archiving && provider && (
        <ArchiveDialog provider={provider} onClose={() => setArchiving(false)} />
      )}
    </Card>
  );
}

function ArchiveDialog({ provider, onClose }: { provider: Provider; onClose: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const archive = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/admin/price-providers/{provider_id}/archive", {
          params: { path: { provider_id: provider.id } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: PROVIDERS_KEY }),
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>
          {t("pages.priceProviders.archiveDialog.title", { name: provider.name })}
        </DialogTitle>
        <DialogDescription>{t("pages.priceProviders.archiveDialog.description")}</DialogDescription>
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
