import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  Outlet,
} from "@tanstack/react-router";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useMe } from "@/auth/auth";
import { AppShell } from "@/components/app-shell";
import { applyLanguage } from "@/i18n";
import { applyTimeZone } from "@/lib/format";
import { DashboardPage } from "@/features/dashboard/dashboard";
import { DraftEditorPage } from "@/features/policies/draft-editor";
import { DraftSummaryPage } from "@/features/policies/summary";
import { PolicyPage } from "@/features/policies/detail";
import { PoliciesPage } from "@/features/policies/list";
import { PortfolioPage } from "@/features/portfolios/detail";
import { PortfoliosPage } from "@/features/portfolios/list";
import { SnapshotPage } from "@/features/portfolios/snapshot";
import { EnterValuesPage } from "@/features/portfolios/values";
import { RebalanceDetailPage } from "@/features/rebalance/detail";
import { RebalancePage } from "@/features/rebalance/rebalance";
import { ConfirmedReportPage, PlanReportPage } from "@/features/rebalance/report";
import { TimelinePage } from "@/features/timeline/timeline";
import { AccountsPage } from "@/pages/accounts";
import { AiReviewersPage } from "@/pages/ai-reviewers";
import { PriceProvidersPage } from "@/pages/price-providers";
import { ChangePasswordPage } from "@/pages/change-password";
import { LoginPage } from "@/pages/login";
import { SettingsPage } from "@/pages/settings";

const rootRoute = createRootRoute({ component: Outlet });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: LoginPage,
});

/** Everything below needs a login; a temporary password must be changed first. */
function AuthGate() {
  const { data: me, isPending } = useMe();
  const { t, i18n } = useTranslation();
  // USR-10: the account's language, the browser's before login or without a choice
  useEffect(() => applyLanguage(me?.language), [me?.language]);
  // USR-11: before rendering, so every date below is shown in the account's time zone
  applyTimeZone(me?.time_zone);
  if (isPending) return <p className="p-6 text-muted-foreground">{t("common.loading")}</p>;
  if (!me) return <Navigate to="/login" />;
  if (me.must_change_password) return <ChangePasswordPage />;
  // Mounted again when the language or time zone changes, so every text and format follows
  return <AppShell key={`${i18n.language} ${me.time_zone ?? ""}`} me={me} />;
}

const appRoute = createRoute({ getParentRoute: () => rootRoute, id: "app", component: AuthGate });

function InvestorOnly({ children }: { children: React.ReactNode }) {
  const { data: me } = useMe();
  if (me && !me.is_investor) return <Navigate to="/accounts" />;
  return <>{children}</>;
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { data: me } = useMe();
  if (!me?.is_admin) return <Navigate to="/" />;
  return <>{children}</>;
}

const dashboardRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  component: () => (
    <InvestorOnly>
      <DashboardPage />
    </InvestorOnly>
  ),
});
const portfoliosRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/portfolios",
  component: () => (
    <InvestorOnly>
      <PortfoliosPage />
    </InvestorOnly>
  ),
});
/** Numeric ID from a path parameter; anything else shows "not found". */
function idParam(value: string): number | null {
  return /^[1-9]\d*$/.test(value) ? Number(value) : null;
}

function NotFound() {
  const { t } = useTranslation();
  return <p className="text-muted-foreground">{t("common.notFound")}</p>;
}

function WithId({ value, render }: { value: string; render: (id: number) => React.ReactNode }) {
  const id = idParam(value);
  return <InvestorOnly>{id === null ? <NotFound /> : render(id)}</InvestorOnly>;
}

const policiesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/policies",
  component: () => (
    <InvestorOnly>
      <PoliciesPage />
    </InvestorOnly>
  ),
});
const policyRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/policies/$policyId",
  component: function Policy() {
    const { policyId } = policyRoute.useParams();
    return <WithId value={policyId} render={(id) => <PolicyPage key={id} policyId={id} />} />;
  },
});
const draftRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/policies/$policyId/draft",
  component: function Draft() {
    const { policyId } = draftRoute.useParams();
    return <WithId value={policyId} render={(id) => <DraftEditorPage key={id} policyId={id} />} />;
  },
});
// POL-17: the summary of the draft, from which it is activated
const draftSummaryRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/policies/$policyId/draft/summary",
  component: function DraftSummary() {
    const { policyId } = draftSummaryRoute.useParams();
    return <WithId value={policyId} render={(id) => <DraftSummaryPage key={id} policyId={id} />} />;
  },
});
const timelineRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/timeline",
  component: () => (
    <InvestorOnly>
      <TimelinePage />
    </InvestorOnly>
  ),
});
const portfolioRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/portfolios/$portfolioId",
  component: function Portfolio() {
    const { portfolioId } = portfolioRoute.useParams();
    return (
      <WithId value={portfolioId} render={(id) => <PortfolioPage key={id} portfolioId={id} />} />
    );
  },
});
const valuesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/portfolios/$portfolioId/values",
  // RB-02: the fresh snapshot a rebalance starts from
  validateSearch: (search: Record<string, unknown>): { rebalance?: boolean } => ({
    rebalance: search.rebalance === true || search.rebalance === "true" ? true : undefined,
  }),
  component: function Values() {
    const { portfolioId } = valuesRoute.useParams();
    const rebalance = valuesRoute.useSearch().rebalance === true;
    return (
      <WithId
        value={portfolioId}
        render={(id) => (
          <EnterValuesPage key={`${id}-${rebalance}`} portfolioId={id} forRebalance={rebalance} />
        )}
      />
    );
  },
});
/** Search parameters are untrusted: only a positive snapshot ID and plain
 * non-negative amounts are used, anything else is ignored. */
function snapshotParam(value: unknown): number | undefined {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : undefined;
}

function amountParam(value: unknown): string | undefined {
  const text = typeof value === "number" || typeof value === "string" ? String(value) : "";
  return /^\d+(\.\d+)?$/.test(text) ? text : undefined;
}

const rebalanceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/portfolios/$portfolioId/rebalance",
  validateSearch: (search: Record<string, unknown>): { snapshot?: number } => ({
    snapshot: snapshotParam(search.snapshot),
  }),
  component: function Rebalance() {
    const { portfolioId } = rebalanceRoute.useParams();
    const snapshot = snapshotParam(rebalanceRoute.useSearch().snapshot);
    // RB-02: a rebalance always starts from a fresh snapshot
    if (snapshot === undefined)
      return (
        <Navigate
          to="/portfolios/$portfolioId/values"
          params={{ portfolioId }}
          search={{ rebalance: true }}
          replace
        />
      );
    return (
      <WithId
        value={portfolioId}
        render={(id) => (
          <RebalancePage key={`${id}-${snapshot}`} portfolioId={id} snapshotId={snapshot} />
        )}
      />
    );
  },
});
const planReportRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/portfolios/$portfolioId/rebalance/report",
  validateSearch: (
    search: Record<string, unknown>,
  ): { snapshot?: number; contribution?: string; withdrawal?: string } => ({
    snapshot: snapshotParam(search.snapshot),
    contribution: amountParam(search.contribution),
    withdrawal: amountParam(search.withdrawal),
  }),
  component: function PlanReport() {
    const { portfolioId } = planReportRoute.useParams();
    const search = planReportRoute.useSearch();
    return (
      <WithId
        value={portfolioId}
        render={(id) => (
          <PlanReportPage
            portfolioId={id}
            snapshotId={snapshotParam(search.snapshot)}
            contribution={amountParam(search.contribution)}
            withdrawal={amountParam(search.withdrawal)}
          />
        )}
      />
    );
  },
});
const confirmedReportRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/rebalances/$rebalanceId/report",
  component: function ConfirmedReport() {
    const { rebalanceId } = confirmedReportRoute.useParams();
    return (
      <WithId
        value={rebalanceId}
        render={(id) => <ConfirmedReportPage key={id} rebalanceId={id} />}
      />
    );
  },
});
const snapshotRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/snapshots/$snapshotId",
  component: function SnapshotRoute() {
    const { snapshotId } = snapshotRoute.useParams();
    return <WithId value={snapshotId} render={(id) => <SnapshotPage key={id} snapshotId={id} />} />;
  },
});
const rebalanceDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/rebalances/$rebalanceId",
  component: function RebalanceDetail() {
    const { rebalanceId } = rebalanceDetailRoute.useParams();
    return (
      <WithId
        value={rebalanceId}
        render={(id) => <RebalanceDetailPage key={id} rebalanceId={id} />}
      />
    );
  },
});
const accountsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/accounts",
  component: () => (
    <AdminOnly>
      <AccountsPage />
    </AdminOnly>
  ),
});
const aiReviewersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/ai-reviewers",
  component: () => (
    <AdminOnly>
      <AiReviewersPage />
    </AdminOnly>
  ),
});
const priceProvidersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/price-providers",
  component: () => (
    <AdminOnly>
      <PriceProvidersPage />
    </AdminOnly>
  ),
});
const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings",
  component: SettingsPage, // every account, at least for the language (USR-10)
});
const passwordRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/password",
  component: ChangePasswordPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([
    dashboardRoute,
    portfoliosRoute,
    portfolioRoute,
    valuesRoute,
    rebalanceRoute,
    planReportRoute,
    confirmedReportRoute,
    snapshotRoute,
    rebalanceDetailRoute,
    policiesRoute,
    policyRoute,
    draftRoute,
    draftSummaryRoute,
    timelineRoute,
    accountsRoute,
    aiReviewersRoute,
    priceProvidersRoute,
    settingsRoute,
    passwordRoute,
  ]),
]);

export function createAppRouter(history?: Parameters<typeof createRouter>[0]["history"]) {
  return createRouter({ routeTree, history });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
