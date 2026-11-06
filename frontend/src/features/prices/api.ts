import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type PriceSource = components["schemas"]["PriceSourceOut"];
export type ListingInfo = components["schemas"]["ListingOut"];
export type LookupResult = components["schemas"]["LookupOut"];

export const priceSourcesKey = ["price-sources"] as const;

/** PRC-05: every asset the investor uses, with its price source. */
export function usePriceSources() {
  return useQuery({
    queryKey: priceSourcesKey,
    queryFn: () => unwrap(api.GET("/api/price-sources")),
  });
}

/** PRC-02, PRC-06: never fails for missing providers; problems come in the result. */
export function useLookup() {
  return useMutation({
    mutationFn: (body: { ticker: string; retry: boolean }) =>
      unwrap(api.POST("/api/price-sources/lookup", { body })),
  });
}

export function useSetSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      ticker,
      ...body
    }: {
      ticker: string;
      kind: "auto" | "manual" | "unresolved";
      listing_id?: number | null;
      name?: string | null;
      type?: string | null;
    }) => unwrap(api.PUT("/api/price-sources/{ticker}", { params: { path: { ticker } }, body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: priceSourcesKey });
      void client.invalidateQueries({ queryKey: ["assets"] }); // may add to the catalog
    },
  });
}
