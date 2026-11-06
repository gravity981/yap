import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";
import { rawBody } from "@/features/theses/api";

export type Policy = components["schemas"]["PolicyOut"];
export type PolicySummary = components["schemas"]["PolicySummary"];
export type Version = components["schemas"]["VersionOut"];
export type PositionIn = components["schemas"]["PositionIn"];

export const policiesKey = ["policies"] as const;
const path = (id: number) => ({ params: { path: { policy_id: id } } });

export function usePolicies() {
  return useQuery({ queryKey: policiesKey, queryFn: () => unwrap(api.GET("/api/policies")) });
}

export function usePolicy(id: number) {
  return useQuery({
    queryKey: ["policies", id],
    queryFn: () => unwrap(api.GET("/api/policies/{policy_id}", path(id))),
  });
}

export function useVersion(policyId: number, versionNo: number | undefined) {
  return useQuery({
    queryKey: ["policies", policyId, "versions", versionNo],
    enabled: versionNo !== undefined,
    queryFn: () =>
      unwrap(
        api.GET("/api/policies/{policy_id}/versions/{version_no}", {
          params: { path: { policy_id: policyId, version_no: versionNo! } },
        }),
      ),
  });
}

export function useCompare(policyId: number, from: number, to: number) {
  return useQuery({
    queryKey: ["policies", policyId, "compare", from, to],
    queryFn: () =>
      unwrap(
        api.GET("/api/policies/{policy_id}/compare", {
          params: { path: { policy_id: policyId }, query: { from_version: from, to_version: to } },
        }),
      ),
  });
}

export function useAssets() {
  return useQuery({ queryKey: ["assets"], queryFn: () => unwrap(api.GET("/api/assets")) });
}

function usePolicyMutation<T, R>(fn: (arg: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: policiesKey });
      client.invalidateQueries({ queryKey: ["assets"] });
      client.invalidateQueries({ queryKey: ["portfolios"] });
      client.invalidateQueries({ queryKey: ["timeline"] });
      // A draft change can confirm, outdate or delete its review (REV-09, REV-11)
      client.invalidateQueries({ queryKey: ["reviews"] });
    },
  });
}

export function useCreatePolicy() {
  return usePolicyMutation((body: { name: string; thesis_id: number }) =>
    unwrap(api.POST("/api/policies", { body })),
  );
}

export function usePolicyActions(id: number) {
  return {
    createDraft: usePolicyMutation(() =>
      unwrap(api.POST("/api/policies/{policy_id}/draft", path(id))),
    ),
    saveDraft: usePolicyMutation((body: { positions: PositionIn[] }) =>
      unwrap(api.PUT("/api/policies/{policy_id}/draft", { ...path(id), body })),
    ),
    deleteDraft: usePolicyMutation(() =>
      unwrap(api.DELETE("/api/policies/{policy_id}/draft", path(id))),
    ),
    activate: usePolicyMutation((change_note: string | null) =>
      unwrap(
        api.POST("/api/policies/{policy_id}/draft/activate", {
          ...path(id),
          body: { change_note },
        }),
      ),
    ),
    adopt: usePolicyMutation(() =>
      unwrap(api.POST("/api/policies/{policy_id}/adopt-thesis-revision", path(id))),
    ),
    archive: usePolicyMutation(() =>
      unwrap(api.POST("/api/policies/{policy_id}/archive", path(id))),
    ),
  };
}

export const targetImport = {
  preview: (text: string, policyId: number) =>
    unwrap(
      api.POST("/api/policies/{policy_id}/import/preview", { ...path(policyId), ...rawBody(text) }),
    ),
  run: (text: string, policyId: number) =>
    unwrap(api.POST("/api/policies/{policy_id}/import", { ...path(policyId), ...rawBody(text) })),
};
