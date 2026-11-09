import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { Button } from "@/components/ui/button";

import { useSnapshot } from "./api";
import { ComparisonView } from "./comparison";

/** CMP-03 to CMP-05, CMP-08: a past snapshot, compared with its own policy version. */
export function SnapshotPage({ snapshotId }: { snapshotId: number }) {
  const { t } = useTranslation();
  const snapshot = useSnapshot(snapshotId);
  if (snapshot.error) return <FormError error={snapshot.error} />;
  if (!snapshot.data) return <p className="text-muted-foreground">{t("common.loading")}</p>;
  const id = String(snapshot.data.portfolio_id);
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t("portfolios.snapshot.title")}</h1>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <a href={`/api/snapshots/${snapshot.data.id}/export`} download>
              {t("portfolios.snapshot.export")}
            </a>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/portfolios/$portfolioId" params={{ portfolioId: id }}>
              {t("portfolios.snapshot.portfolio")}
            </Link>
          </Button>
          <Button asChild>
            {/* RB-02: from the latest snapshot, not necessarily from this one */}
            <Link to="/portfolios/$portfolioId/rebalance" params={{ portfolioId: id }}>
              {t("portfolios.snapshot.rebalance")}
            </Link>
          </Button>
        </div>
      </div>
      <ComparisonView snapshot={snapshot.data} />
    </div>
  );
}
