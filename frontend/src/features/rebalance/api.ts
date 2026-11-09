import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Plan = components["schemas"]["PlanOut"];
export type Result = components["schemas"]["ResultOut"];
export type Rebalance = components["schemas"]["RebalanceOut"];

export function usePlan(
  portfolioId: number,
  snapshotId: number | undefined,
  contribution: string | undefined,
  withdrawal?: string,
  mode?: string,
) {
  return useQuery({
    queryKey: ["portfolios", portfolioId, "plan", snapshotId, contribution, withdrawal, mode],
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/portfolios/{portfolio_id}/rebalance", {
          params: {
            path: { portfolio_id: portfolioId },
            query: {
              snapshot_id: snapshotId ?? null,
              contribution: contribution ?? null,
              withdrawal: withdrawal ?? null,
              mode: mode ?? null,
            },
          },
        }),
      ),
  });
}

export function useConfirm(portfolioId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      snapshot_id: number;
      contribution: string;
      withdrawal: string;
      mode: string;
      policy_version_id: number;
    }) =>
      unwrap(
        api.POST("/api/portfolios/{portfolio_id}/rebalances", {
          params: { path: { portfolio_id: portfolioId } },
          body,
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["timeline"] });
    },
  });
}

export function useSimulation(portfolioId: number) {
  return useMutation({
    mutationFn: (body: {
      cycles: number;
      contribution: string;
      withdrawal: string;
      snapshot_id: number;
    }) =>
      unwrap(
        api.POST("/api/portfolios/{portfolio_id}/simulate", {
          params: { path: { portfolio_id: portfolioId } },
          body,
        }),
      ),
  });
}

export function useRebalance(id: number) {
  return useQuery({
    queryKey: ["rebalances", id],
    queryFn: () =>
      unwrap(api.GET("/api/rebalances/{rebalance_id}", { params: { path: { rebalance_id: id } } })),
  });
}
