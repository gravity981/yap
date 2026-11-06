import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { FileImport } from "@/components/file-import";
import { filePositions, ImportPriceSources } from "@/features/prices/import-price-sources";
import { Field, FormError, fieldError } from "@/components/form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePolicies } from "@/features/policies/api";
import { formatDateTime } from "@/lib/format";

import {
  currentImport,
  usePortfolio,
  usePortfolioActions,
  useSnapshots,
  type Portfolio,
  type PositionSettings,
} from "./api";
import { ComparisonView, sourceLabel } from "./comparison";

/** PTF-05: policy, active version, assignment history, latest snapshot. */
export function PortfolioPage({ portfolioId }: { portfolioId: number }) {
  const { t } = useTranslation();
  const portfolio = usePortfolio(portfolioId);
  const snapshots = useSnapshots(portfolioId);
  const client = useQueryClient();
  const [dialog, setDialog] = useState<"settings" | "import" | null>(null);
  const [tab, setTab] = useState("current");

  if (portfolio.error) return <FormError error={portfolio.error} />;
  if (!portfolio.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const p = portfolio.data;
  const id = String(p.id);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">
            {p.name}{" "}
            {p.archived_at && <Badge variant="secondary">{t("portfolios.detail.archived")}</Badge>}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("portfolios.detail.policy")}{" "}
            <Link
              to="/policies/$policyId"
              params={{ policyId: String(p.policy_id) }}
              className="underline"
            >
              {p.policy_name}
            </Link>{" "}
            {t("portfolios.detail.active", { version: p.active_version_label ?? "–" })}{" "}
            {t("portfolios.detail.currency", { currency: p.currency })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setDialog("settings")}>
            {t("portfolios.detail.settings")}
          </Button>
          <Button variant="outline" onClick={() => setDialog("import")}>
            {t("portfolios.detail.importValues")}
          </Button>
          <Button variant="outline" asChild>
            <Link to="/portfolios/$portfolioId/values" params={{ portfolioId: id }}>
              {t("portfolios.detail.enterValues")}
            </Link>
          </Button>
          <Button asChild>
            <Link
              to="/portfolios/$portfolioId/values"
              params={{ portfolioId: id }}
              search={{ rebalance: true }}
            >
              {t("portfolios.detail.rebalance")}
            </Link>
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="current">{t("portfolios.detail.current")}</TabsTrigger>
          <TabsTrigger value="history">{t("portfolios.detail.history")}</TabsTrigger>
        </TabsList>
        <TabsContent value="current">
          {p.latest_snapshot ? (
            <ComparisonView snapshot={p.latest_snapshot} precise={p.precise_amounts} />
          ) : (
            <p className="text-muted-foreground">{t("portfolios.detail.noValues")}</p>
          )}
        </TabsContent>
        <TabsContent value="history" className="grid gap-6">
          <section className="grid gap-2">
            <h2 className="font-semibold">{t("portfolios.detail.snapshots")}</h2>
            <ul className="grid gap-1 text-sm">
              {snapshots.data?.map((s) => (
                <li key={s.id}>
                  <Link
                    to="/snapshots/$snapshotId"
                    params={{ snapshotId: String(s.id) }}
                    className="underline"
                  >
                    {formatDateTime(s.taken_at)}
                  </Link>{" "}
                  <span className="text-muted-foreground">
                    {s.policy_version_label} · {sourceLabel(s.source)}
                    {s.corrects_snapshot_id !== null && t("portfolios.detail.correction")}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section className="grid gap-2">
            <h2 className="font-semibold">{t("portfolios.detail.assignments")}</h2>
            <ul className="grid gap-1 text-sm">
              {p.assignments.map((a) => (
                <li key={a.valid_from}>
                  {a.policy_name}{" "}
                  <span className="text-muted-foreground">
                    {t("portfolios.detail.from", { date: formatDateTime(a.valid_from) })}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </TabsContent>
      </Tabs>

      {dialog === "settings" && <SettingsDialog portfolio={p} onClose={() => setDialog(null)} />}
      {dialog === "import" && (
        <FileImport
          title={t("portfolios.detail.importTitle")}
          description={t("portfolios.detail.importDescription", { name: p.name })}
          preview={async (text) => ({
            ...(await currentImport.preview(text, p.id)),
            positions: filePositions(text),
          })}
          run={(text) => currentImport.run(text, p.id)}
          renderPreview={(preview) => (
            <div className="grid gap-4">
              <div className="grid gap-1 text-sm">
                <p>{t("portfolios.detail.importValuesCount", { n: preview.values.length })}</p>
                {preview.new_tickers.length > 0 && (
                  <p>
                    {t("portfolios.detail.importNewTickers", {
                      tickers: preview.new_tickers.join(", "),
                    })}
                  </p>
                )}
              </div>
              <ImportPriceSources positions={preview.positions} />
            </div>
          )}
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            setTab("current");
            // Like the other portfolio changes; the import may add tickers to the catalog
            for (const key of [["portfolios"], ["policies"], ["timeline"], ["assets"]]) {
              void client.invalidateQueries({ queryKey: key });
            }
          }}
        />
      )}
    </div>
  );
}

/** PTF-03, PTF-04, PTF-06 */
function SettingsDialog({ portfolio, onClose }: { portfolio: Portfolio; onClose: () => void }) {
  const { t } = useTranslation();
  const actions = usePortfolioActions(portfolio.id);
  const policies = usePolicies();
  const [contribution, setContribution] = useState(portfolio.default_contribution);
  const [precise, setPrecise] = useState(portfolio.precise_amounts);
  const [currency, setCurrency] = useState(portfolio.currency);
  const [positions, setPositions] = useState<Record<string, PositionSettings>>(() =>
    Object.fromEntries(
      portfolio.positions.map((p) => [
        p.ticker,
        { broker: p.broker ?? "", whole_units: p.whole_units },
      ]),
    ),
  );
  const setPosition = (ticker: string, patch: PositionSettings) =>
    setPositions((all) => ({ ...all, [ticker]: { ...all[ticker], ...patch } }));
  const [policyId, setPolicyId] = useState(String(portfolio.policy_id));
  const error =
    actions.settings.error ??
    actions.positions.error ??
    actions.reassign.error ??
    actions.archive.error;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await actions.settings.mutateAsync({
      default_contribution: contribution,
      precise_amounts: precise,
      currency,
    });
    await actions.positions.mutateAsync(positions);
    if (Number(policyId) !== portfolio.policy_id)
      await actions.reassign.mutateAsync(Number(policyId));
    onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-auto">
        <DialogTitle>{t("portfolios.settings.title", { name: portfolio.name })}</DialogTitle>
        <DialogDescription>{t("portfolios.settings.description")}</DialogDescription>
        <form className="mt-4 grid gap-4" onSubmit={(e) => submit(e).catch(() => undefined)}>
          <Field
            id="settings-contribution"
            label={t("portfolios.settings.contribution")}
            error={fieldError(actions.settings.error, "default_contribution")}
          >
            <Input
              id="settings-contribution"
              inputMode="decimal"
              value={contribution}
              onChange={(e) => setContribution(e.target.value)}
              required
            />
          </Field>
          <Field
            id="settings-currency"
            label={t("portfolios.settings.currency")}
            hint={portfolio.currency_locked ? t("portfolios.settings.currencyLocked") : undefined}
            error={fieldError(actions.settings.error, "currency")}
          >
            <Input
              id="settings-currency"
              className="w-24 uppercase"
              maxLength={3}
              value={currency}
              disabled={portfolio.currency_locked}
              onChange={(e) => setCurrency(e.target.value)}
              required
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={precise}
              onChange={(e) => setPrecise(e.target.checked)}
            />
            {t("portfolios.settings.precise")}
          </label>
          <Field id="settings-policy" label={t("portfolios.settings.policy")}>
            <NativeSelect
              id="settings-policy"
              value={policyId}
              onChange={(e) => setPolicyId(e.target.value)}
            >
              {(policies.data ?? [])
                .filter(
                  (p) => p.id === portfolio.policy_id || (p.active_version_label && !p.archived_at),
                )
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </NativeSelect>
          </Field>
          {portfolio.positions.length > 0 && (
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">{t("portfolios.settings.positions")}</legend>
              {portfolio.positions.map(({ ticker }) => {
                const settings = positions[ticker] ?? { broker: "", whole_units: null };
                return (
                  <div
                    key={ticker}
                    className="grid grid-cols-[5rem_1fr] items-center gap-x-2 gap-y-1 text-sm sm:grid-cols-[5rem_1fr_auto]"
                  >
                    <span>{ticker}</span>
                    <Input
                      aria-label={t("portfolios.settings.brokerOf", { ticker })}
                      value={settings.broker ?? ""}
                      onChange={(e) => setPosition(ticker, { broker: e.target.value })}
                    />
                    {/* Not for the cash buffer, which has only an amount (PTF-03) */}
                    {settings.whole_units !== null && (
                      <label
                        className="col-start-2 flex items-center gap-2 sm:col-start-auto"
                        title={t("portfolios.settings.wholeUnitsOf", { ticker })}
                      >
                        <input
                          type="checkbox"
                          aria-label={t("portfolios.settings.wholeUnitsOf", { ticker })}
                          checked={settings.whole_units ?? false}
                          onChange={(e) => setPosition(ticker, { whole_units: e.target.checked })}
                        />
                        {t("portfolios.settings.wholeUnits")}
                      </label>
                    )}
                  </div>
                );
              })}
            </fieldset>
          )}
          <FormError error={error} fields={["default_contribution", "currency"]} />
          <div className="flex flex-wrap justify-between gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={portfolio.archived_at !== null}
              onClick={() => actions.archive.mutate(undefined, { onSuccess: onClose })}
            >
              {t("portfolios.settings.archive")}
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                {t("common.cancel")}
              </Button>
              <Button type="submit">{t("common.save")}</Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
