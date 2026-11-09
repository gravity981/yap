import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";
import { rawBody } from "@/features/policies/api";

export type PortfolioSummary = components["schemas"]["PortfolioSummary"];
export type Portfolio = components["schemas"]["PortfolioOut"];
export type Snapshot = components["schemas"]["SnapshotOut"];
export type SnapshotListItem = components["schemas"]["SnapshotListItem"];
export type PrefillRow = components["schemas"]["PrefillRowOut"];
export type ValueIn = components["schemas"]["ValueIn"];
export type PositionSettings = components["schemas"]["PositionSettingsIn"];

export const portfoliosKey = ["portfolios"] as const;
const path = (id: number) => ({ params: { path: { portfolio_id: id } } });

export function usePortfolios() {
  return useQuery({ queryKey: portfoliosKey, queryFn: () => unwrap(api.GET("/api/portfolios")) });
}

export function usePortfolio(id: number) {
  return useQuery({
    queryKey: ["portfolios", id],
    queryFn: () => unwrap(api.GET("/api/portfolios/{portfolio_id}", path(id))),
  });
}

export function usePrefill(id: number) {
  return useQuery({
    queryKey: ["portfolios", id, "prefill"],
    queryFn: () => unwrap(api.GET("/api/portfolios/{portfolio_id}/prefill", path(id))),
    staleTime: 0,
  });
}

export function useSnapshots(id: number) {
  return useQuery({
    queryKey: ["portfolios", id, "snapshots"],
    queryFn: () => unwrap(api.GET("/api/portfolios/{portfolio_id}/snapshots", path(id))),
  });
}

export function useSnapshot(id: number) {
  return useQuery({
    queryKey: ["snapshots", id],
    queryFn: () =>
      unwrap(api.GET("/api/snapshots/{snapshot_id}", { params: { path: { snapshot_id: id } } })),
  });
}

function usePortfolioMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of [portfoliosKey, ["policies"], ["timeline"], ["assets"], ["snapshots"]]) {
        client.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export function useCreatePortfolio() {
  return usePortfolioMutation(
    (body: {
      name: string;
      policy_id: number;
      currency: string;
      default_contribution: string;
      precise_amounts: boolean;
    }) => unwrap(api.POST("/api/portfolios", { body })),
  );
}

export function usePortfolioActions(id: number) {
  return {
    settings: usePortfolioMutation(
      (body: { default_contribution: string; precise_amounts: boolean; currency: string }) =>
        unwrap(api.PUT("/api/portfolios/{portfolio_id}/settings", { ...path(id), body })),
    ),
    positions: usePortfolioMutation((body: Record<string, PositionSettings>) =>
      unwrap(api.PUT("/api/portfolios/{portfolio_id}/positions", { ...path(id), body })),
    ),
    reassign: usePortfolioMutation((policy_id: number) =>
      unwrap(
        api.POST("/api/portfolios/{portfolio_id}/reassign", { ...path(id), body: { policy_id } }),
      ),
    ),
    archive: usePortfolioMutation(() =>
      unwrap(api.POST("/api/portfolios/{portfolio_id}/archive", path(id))),
    ),
    snapshot: usePortfolioMutation(
      (body: { values: ValueIn[]; corrects_snapshot_id: number | null }) =>
        unwrap(api.POST("/api/portfolios/{portfolio_id}/snapshots", { ...path(id), body })),
    ),
  };
}

export const currentImport = {
  preview: (text: string, id: number) =>
    unwrap(
      api.POST("/api/portfolios/{portfolio_id}/import/preview", { ...path(id), ...rawBody(text) }),
    ),
  run: (text: string, id: number) =>
    unwrap(api.POST("/api/portfolios/{portfolio_id}/import", { ...path(id), ...rawBody(text) })),
};
