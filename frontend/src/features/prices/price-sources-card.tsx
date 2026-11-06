import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormError } from "@/components/form";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime, formatPrice } from "@/lib/format";

import { usePriceSources } from "./api";
import { StaleMarker } from "./auto-price";
import { PriceSourceControl, SourceBadge } from "./price-source";

/** PRC-05, PRC-06: the price source of every asset the investor uses; change the listing,
 * switch to manual, or try auto. */
export function PriceSourcesCard() {
  const { t } = useTranslation();
  const sources = usePriceSources();
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <Card>
      <CardContent className="grid gap-4 pt-5">
        <div className="grid gap-1">
          <h2 className="text-lg font-semibold">{t("prices.settings.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("prices.settings.description")}</p>
        </div>
        <FormError error={sources.error} />
        {sources.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("prices.settings.none")}</p>
        )}
        {sources.data && sources.data.length > 0 && (
          <Table aria-label={t("prices.settings.title")}>
            <TableHeader>
              <TableRow>
                <TableHead>{t("prices.settings.asset")}</TableHead>
                <TableHead>{t("prices.settings.source")}</TableHead>
                <TableHead className="text-right">{t("prices.settings.price")}</TableHead>
                <TableHead>{t("prices.settings.updated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.data.map((s) => {
                const listing = s.kind === "auto" ? s.listing : null;
                return (
                  <TableRow key={s.ticker}>
                    <TableCell>
                      <span className="font-medium">{s.ticker}</span>{" "}
                      <span className="text-muted-foreground">{s.name}</span>
                    </TableCell>
                    <TableCell className="grid gap-1">
                      {editing === s.ticker ? (
                        <PriceSourceControl
                          ticker={s.ticker}
                          editable
                          onChosen={() => setEditing(null)}
                        />
                      ) : (
                        <span className="flex flex-wrap items-center gap-2">
                          <SourceBadge source={s} />
                          <button
                            type="button"
                            className="text-xs underline"
                            onClick={() => setEditing(s.ticker)}
                          >
                            {t("prices.settings.change", { ticker: s.ticker })}
                          </button>
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {listing?.price ? `${formatPrice(listing.price)} ${listing.currency}` : "–"}{" "}
                      {listing?.price_date && <StaleMarker date={listing.price_date} />}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {listing?.price_updated_at ? formatDateTime(listing.price_updated_at) : "–"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
