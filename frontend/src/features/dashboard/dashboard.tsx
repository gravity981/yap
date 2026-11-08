import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { PageTitle } from "@/components/page-title";
import { Alert } from "@/components/ui/alert";
import { usePolicies } from "@/features/policies/api";
import { usePortfolios } from "@/features/portfolios/api";
import { PortfolioCards } from "@/features/portfolios/list";
import { semaphoreLabel } from "@/features/reviews/semaphore";
import { EventList } from "@/features/timeline/timeline";
import { useTimeline } from "@/features/timeline/api";

const RECENT = 8;

/** Start page (UI decision, section 2.3): portfolios, warnings, recent events. */
export function DashboardPage() {
  const { t } = useTranslation();
  const portfolios = usePortfolios();
  const policies = usePolicies();
  const events = useTimeline({ types: [] });
  const warnings = (policies.data ?? []).filter((p) => !p.archived_at && p.thesis_warning);

  return (
    <div className="grid gap-6">
      <PageTitle
        title={t("portfolios.dashboard.title")}
        description={t("portfolios.dashboard.description")}
      />
      <section className="grid gap-3">
        <h2 className="font-semibold">{t("portfolios.dashboard.portfolios")}</h2>
        <FormError error={portfolios.error} />
        {portfolios.data && <PortfolioCards portfolios={portfolios.data} />}
      </section>
      {warnings.length > 0 && (
        <section className="grid gap-2">
          <h2 className="font-semibold">{t("portfolios.dashboard.warnings")}</h2>
          {warnings.map((p) => (
            <Alert key={p.id} variant="warning">
              <Link
                to="/policies/$policyId"
                params={{ policyId: String(p.id) }}
                className="font-medium underline"
              >
                {p.name}
              </Link>
              {t("portfolios.dashboard.thesisMarked", {
                status: semaphoreLabel(p.semaphore),
              })}
            </Alert>
          ))}
        </section>
      )}
      <section className="grid gap-2">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">{t("portfolios.dashboard.recentEvents")}</h2>
          <Link to="/timeline" className="text-sm underline">
            {t("portfolios.dashboard.timeline")}
          </Link>
        </div>
        {events.data && <EventList events={[...events.data].reverse().slice(0, RECENT)} compact />}
      </section>
    </div>
  );
}
