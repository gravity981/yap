import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type TimelineEvent = components["schemas"]["EventOut"];

// The event types; their labels are timeline.types.* in src/i18n/areas/timeline.ts
export const EVENT_TYPES = [
  "policy_activated",
  "portfolio_assigned",
  "rebalance_confirmed",
  "thesis_review_confirmed",
  "policy_review_confirmed",
  "thesis_revised",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

export interface TimelineFilter {
  portfolioId?: number;
  policyId?: number;
  types: EventType[];
  start?: string; // UTC ISO
  end?: string;
}

export function useTimeline(filter: TimelineFilter) {
  return useQuery({
    queryKey: ["timeline", filter],
    queryFn: () =>
      unwrap(
        api.GET("/api/timeline", {
          params: {
            query: {
              portfolio_id: filter.portfolioId ?? null,
              policy_id: filter.policyId ?? null,
              type: filter.types.length ? filter.types : null,
              start: filter.start ?? null,
              end: filter.end ?? null,
            },
          },
        }),
      ),
  });
}

export function useVersionById(id: number | null) {
  return useQuery({
    queryKey: ["policy-versions", id],
    enabled: id !== null,
    queryFn: () =>
      unwrap(
        api.GET("/api/policy-versions/{version_id}", { params: { path: { version_id: id! } } }),
      ),
  });
}
