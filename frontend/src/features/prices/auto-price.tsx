import { Clock } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { formatDate, formatPrice } from "@/lib/format";

export type AutoPrice = components["schemas"]["AutoPriceOut"];

const STALE_DAYS = 3;
const DAY_MS = 24 * 60 * 60 * 1000;

/** PRC-12: more than 3 days older than `reference` (now, or when a snapshot was taken). */
export function isStale(priceDate: string, reference: Date = new Date()): boolean {
  const day = new Date(`${priceDate}T00:00:00Z`);
  const today = Date.UTC(
    reference.getUTCFullYear(),
    reference.getUTCMonth(),
    reference.getUTCDate(),
  );
  return (today - day.getTime()) / DAY_MS > STALE_DAYS;
}

/** PRC-12: a small marker with the date as tooltip; no dialog, no blocking warning. */
export function StaleMarker({ date, reference }: { date: string; reference?: Date }) {
  const { t } = useTranslation();
  if (!isStale(date, reference)) return null;
  const label = t("prices.stale", { date: formatDate(`${date}T12:00:00Z`) });
  return (
    <span title={label} aria-label={label} role="img" className="inline-flex text-warning">
      <Clock className="size-3.5" aria-hidden />
    </span>
  );
}

/** CMP-01, CMP-10: where an auto price came from: listing, its own price and currency, the
 * exchange rate if converted, and the provider's date. */
export function AutoPriceInfo({
  auto,
  currency,
  reference,
}: {
  auto: AutoPrice;
  currency: string;
  reference?: Date;
}) {
  const { t } = useTranslation();
  const values = {
    symbol: auto.symbol,
    price: formatPrice(auto.listing_price),
    currency: auto.listing_currency,
    rate: auto.fx_rate,
    target: currency,
    date: formatDate(`${auto.price_date}T12:00:00Z`),
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
      {auto.listing_currency === currency
        ? t("prices.auto.same", values)
        : t("prices.auto.converted", values)}
      <StaleMarker date={auto.price_date} reference={reference} />
    </span>
  );
}

/** PRC-09, PRC-11: why a position has no auto price; the investor enters it. */
export function PriceNotice({ notice, symbol }: { notice: string; symbol: string | null }) {
  const { t } = useTranslation();
  const key =
    notice === "unavailable"
      ? "prices.notice.unavailable"
      : notice === "no_rate"
        ? "prices.notice.noRate"
        : "prices.notice.noPrice";
  return <p className="text-xs text-warning">{t(key, { symbol: symbol ?? "" })}</p>;
}
