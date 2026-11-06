import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { translateMessage } from "@/api/client";
import { FormError } from "@/components/form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";

import {
  useLookup,
  usePriceSources,
  useSetSource,
  type ListingInfo,
  type LookupResult,
  type PriceSource,
} from "./api";

/** "VWRL.SW · SIX · CHF (Yahoo Finance)" */
export function listingLabel(listing: ListingInfo): string {
  return `${listing.symbol} · ${listing.exchange} · ${listing.currency} (${listing.provider_name})`;
}

/** PRC-05: where the prices of an asset come from. */
export function SourceBadge({ source }: { source: PriceSource | undefined }) {
  const { t } = useTranslation();
  if (!source?.kind) return <Badge variant="outline">{t("prices.source.none")}</Badge>;
  if (source.kind === "auto" && source.listing)
    return (
      <Badge variant={source.listing.available ? "success" : "warning"}>
        {listingLabel(source.listing)}
      </Badge>
    );
  // PRC-09: a manual source that keeps its listing lost it
  if (source.kind === "manual" && source.listing && !source.listing.available)
    return (
      <Badge variant="warning">
        {t("prices.source.retired", { symbol: source.listing.symbol })}
      </Badge>
    );
  return (
    <Badge variant={source.kind === "unresolved" ? "warning" : "secondary"}>
      {t(source.kind === "unresolved" ? "prices.source.unresolved" : "prices.source.manual")}
    </Badge>
  );
}

const DEBOUNCE_MS = 800;

function useDebounced(value: string): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value]);
  return debounced;
}

/** PRC-02 to PRC-04, PRC-06: the price source of a ticker in a form. A ticker without one is
 * looked up as soon as it is entered: one listing becomes the source, none means manual, a
 * failed lookup unresolved; with several, the investor chooses. `name` and `type` are
 * needed only for tickers new to the catalog; `onName` gets a found listing's name for
 * them (IMP-08). */
export function PriceSourceControl({
  ticker,
  name,
  type,
  onName,
  editable = false,
  onChosen,
}: {
  ticker: string;
  name?: string;
  type?: string;
  onName?: (name: string) => void;
  /** Settings (PRC-05): also choose another listing, or switch to manual. */
  editable?: boolean;
  /** After the investor chose a listing or manual. */
  onChosen?: () => void;
}) {
  const { t } = useTranslation();
  const normalized = ticker.trim().toUpperCase();
  const settled = useDebounced(normalized);
  const sources = usePriceSources();
  const current = sources.data?.find((s) => s.ticker === normalized);
  const lookup = useLookup();
  const choose = useSetSource();
  const [result, setResult] = useState<LookupResult | null>(null);

  const apply = (
    r: LookupResult,
    kind: "auto" | "manual" | "unresolved",
    listing?: ListingInfo,
  ) => {
    const label = listing?.name;
    if (label && !name) onName?.(label);
    choose.mutate({
      ticker: r.ticker,
      kind,
      listing_id: listing?.id ?? null,
      name: name || label || r.ticker,
      type: type ?? null,
    });
  };
  const run = (retry: boolean) =>
    lookup.mutate(
      { ticker: normalized, retry },
      {
        onSuccess: (r) => {
          setResult(r);
          if (r.source?.kind) return; // the investor has chosen already
          if (r.status === "found" && r.listings.length === 1) apply(r, "auto", r.listings[0]);
          else if (r.status === "not_found") apply(r, "manual");
          else if (r.status === "unresolved") apply(r, "unresolved");
        },
      },
    );

  useEffect(() => {
    if (!settled || settled !== normalized || !sources.data || current?.kind) return;
    if (result?.ticker === settled || lookup.isPending) return;
    run(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per settled ticker
  }, [settled, normalized, sources.data, current?.kind]);

  if (!normalized) return null;
  // Several listings found for a new ticker, or any found by "try auto" or in the settings
  const choosing =
    result?.ticker === normalized &&
    result.status === "found" &&
    (editable || (current?.kind ? current.kind !== "auto" : result.listings.length > 1));
  return (
    <div
      className="grid gap-1 text-xs"
      aria-label={t("prices.control.label", { ticker: normalized })}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground">{t("prices.control.source")}</span>
        {lookup.isPending ? (
          <span className="text-muted-foreground">{t("prices.control.lookingUp")}</span>
        ) : (
          <SourceBadge source={current} />
        )}
        {current?.kind && (current.kind !== "auto" || editable) && (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs"
            onClick={() => {
              setResult(null);
              run(true);
            }}
          >
            {current.kind === "auto" ? t("prices.control.another") : t("prices.control.tryAuto")}
          </Button>
        )}
      </div>
      {choosing && result && (
        <ListingChooser
          result={result}
          onChoose={(listing) => {
            apply(result, listing ? "auto" : "manual", listing);
            setResult(null);
            onChosen?.();
          }}
        />
      )}
      {result?.ticker === normalized &&
        result.problems.map((p) => (
          <p key={p.provider + p.code} className="text-muted-foreground">
            {translateMessage(p.code, p.params, p.message)}
          </p>
        ))}
      <FormError error={lookup.error ?? choose.error} />
    </div>
  );
}

/** PRC-02: choose one of several listings, or enter prices by hand. */
export function ListingChooser({
  result,
  onChoose,
}: {
  result: LookupResult;
  onChoose: (listing: ListingInfo | undefined) => void;
}) {
  const { t } = useTranslation();
  const [chosen, setChosen] = useState(String(result.listings[0]?.id ?? ""));
  return (
    <div className="flex flex-wrap items-center gap-2">
      <NativeSelect
        aria-label={t("prices.control.choose", { ticker: result.ticker })}
        className="h-8 w-auto text-xs"
        value={chosen}
        onChange={(e) => setChosen(e.target.value)}
      >
        {result.listings.map((listing) => (
          <option key={listing.id} value={listing.id}>
            {listingLabel(listing)}
          </option>
        ))}
        <option value="manual">{t("prices.control.manual")}</option>
      </NativeSelect>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-8"
        onClick={() => onChoose(result.listings.find((l) => String(l.id) === chosen))}
      >
        {t("prices.control.use")}
      </Button>
    </div>
  );
}
