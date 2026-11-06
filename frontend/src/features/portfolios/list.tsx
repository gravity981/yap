import { Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Field, FormError, fieldError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { useMe } from "@/auth/auth";
import { usePolicies } from "@/features/policies/api";
import { formatDateTime } from "@/lib/format";

import { useCreatePortfolio, usePortfolios, type PortfolioSummary } from "./api";
import { outsideBand } from "./comparison";

/** CMP-09: all portfolios with policy and the band status of the latest snapshot. */
export function PortfolioCards({ portfolios }: { portfolios: PortfolioSummary[] }) {
  const { t } = useTranslation();
  if (portfolios.length === 0)
    return <p className="text-muted-foreground">{t("portfolios.list.none")}</p>;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {portfolios.map((p) => {
        const latest = p.latest_snapshot;
        const outside = latest ? outsideBand(latest) : 0;
        return (
          <Card key={p.id}>
            <CardHeader>
              <CardTitle>
                <Link
                  to="/portfolios/$portfolioId"
                  params={{ portfolioId: String(p.id) }}
                  className="hover:underline"
                >
                  {p.name}
                </Link>{" "}
                {p.archived_at && (
                  <Badge variant="secondary">{t("portfolios.list.archived")}</Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-1 text-sm">
              <span className="text-muted-foreground">
                {t("portfolios.list.policy", { name: p.policy_name })}
              </span>
              {latest ? (
                <>
                  <span>
                    {outside === 0 ? (
                      <Badge variant="success">{t("portfolios.list.allWithinBand")}</Badge>
                    ) : (
                      <Badge variant="warning">
                        {t("portfolios.list.outsideBand", { count: outside })}
                      </Badge>
                    )}
                  </span>
                  <span className="text-muted-foreground">
                    {t("portfolios.list.valuesFrom", {
                      date: formatDateTime(latest.taken_at),
                      version: latest.policy_version_label,
                    })}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground">{t("portfolios.list.noValues")}</span>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export function PortfoliosPage() {
  const { t } = useTranslation();
  const portfolios = usePortfolios();
  const [creating, setCreating] = useState(false);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <PageTitle
          title={t("portfolios.list.title")}
          description={t("portfolios.list.description")}
        />
        <Button onClick={() => setCreating(true)}>{t("portfolios.list.new")}</Button>
      </div>
      <FormError error={portfolios.error} />
      {portfolios.data && <PortfolioCards portfolios={portfolios.data} />}
      {creating && <NewPortfolioDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function NewPortfolioDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const policies = usePolicies();
  const create = useCreatePortfolio();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [policyId, setPolicyId] = useState("");
  const [contribution, setContribution] = useState("0");
  const { data: me } = useMe();
  // PTF-03: preset with the base currency, can be changed
  const [currency, setCurrency] = useState(me?.base_currency ?? "");
  const assignable = (policies.data ?? []).filter((p) => p.active_version_label && !p.archived_at);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(
      {
        name,
        policy_id: Number(policyId),
        currency,
        default_contribution: contribution,
        precise_amounts: false,
      },
      {
        onSuccess: (p) =>
          navigate({ to: "/portfolios/$portfolioId", params: { portfolioId: String(p.id) } }),
      },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{t("portfolios.create.title")}</DialogTitle>
        <DialogDescription>{t("portfolios.create.description")}</DialogDescription>
        <form className="mt-4 grid gap-4" onSubmit={submit}>
          <Field
            id="portfolio-name"
            label={t("portfolios.create.name")}
            error={fieldError(create.error, "name")}
          >
            <Input
              id="portfolio-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </Field>
          <Field id="portfolio-policy" label={t("portfolios.create.policy")}>
            <NativeSelect
              id="portfolio-policy"
              value={policyId}
              onChange={(e) => setPolicyId(e.target.value)}
              required
            >
              <option value="" disabled>
                {t("portfolios.create.choosePolicy")}
              </option>
              {assignable.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.active_version_label})
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field
            id="portfolio-contribution"
            label={t("portfolios.create.contribution")}
            error={fieldError(create.error, "default_contribution")}
          >
            <Input
              id="portfolio-contribution"
              inputMode="decimal"
              value={contribution}
              onChange={(e) => setContribution(e.target.value)}
              required
            />
          </Field>
          <Field
            id="portfolio-currency"
            label={t("portfolios.create.currency")}
            hint={t("portfolios.create.currencyHint")}
            error={fieldError(create.error, "currency")}
          >
            <Input
              id="portfolio-currency"
              className="w-24 uppercase"
              maxLength={3}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              required
            />
          </Field>
          <FormError error={create.error} fields={["name", "default_contribution", "currency"]} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {t("portfolios.create.create")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
