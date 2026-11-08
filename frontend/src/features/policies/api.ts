import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Policy = components["schemas"]["PolicyOut"];
export type PolicySummary = components["schemas"]["PolicySummary"];
export type Version = components["schemas"]["VersionOut"];
export type PositionIn = components["schemas"]["PositionIn"];
export type ThesisIn = components["schemas"]["ThesisIn"];

/** A raw JSON file as request body (imports). */
export function rawBody(text: string) {
  return { body: text as never, bodySerializer: (b: unknown) => b as string };
}

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

/** POL-01: draft v1 holds the thesis template in the account's language. */
export function useCreatePolicy() {
  return usePolicyMutation((body: { name: string; thesis_md: string }) =>
    unwrap(api.POST("/api/policies", { body })),
  );
}

export function usePolicyActions(id: number) {
  return {
    createDraft: usePolicyMutation(() =>
      unwrap(api.POST("/api/policies/{policy_id}/draft", path(id))),
    ),
    saveDraft: usePolicyMutation((body: { positions: PositionIn[]; thesis?: ThesisIn }) =>
      unwrap(api.PUT("/api/policies/{policy_id}/draft", { ...path(id), body })),
    ),
    deleteDraft: usePolicyMutation(() =>
      unwrap(api.DELETE("/api/policies/{policy_id}/draft", path(id))),
    ),
    // POL-14, POL-17: the change note is saved like every other change of the draft
    saveChangeNote: usePolicyMutation((change_note: string | null) =>
      unwrap(
        api.PUT("/api/policies/{policy_id}/draft/change-note", {
          ...path(id),
          body: { change_note },
        }),
      ),
    ),
    activate: usePolicyMutation((change_note: string | null) =>
      unwrap(
        api.POST("/api/policies/{policy_id}/draft/activate", {
          ...path(id),
          body: { change_note },
        }),
      ),
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

/** IMP-01: a thesis file becomes a new policy, or the thesis of the policy's draft. */
export const thesisImport = {
  preview: (text: string, policyId?: number) =>
    policyId === undefined
      ? unwrap(api.POST("/api/policies/import-thesis/preview", rawBody(text)))
      : unwrap(
          api.POST("/api/policies/{policy_id}/import-thesis/preview", {
            ...path(policyId),
            ...rawBody(text),
          }),
        ),
  /** A new policy whose draft v1 holds the thesis. */
  runNew: (text: string) => unwrap(api.POST("/api/policies/import-thesis", rawBody(text))),
  /** The thesis of the policy's draft (created if there is none). */
  runIntoDraft: (text: string, policyId: number) =>
    unwrap(
      api.POST("/api/policies/{policy_id}/import-thesis", { ...path(policyId), ...rawBody(text) }),
    ),
};

/** POL-18: private, text or all. */
export function usePolicySharing(id: number) {
  return usePolicyMutation((sharing: string) =>
    unwrap(api.PUT("/api/policies/{policy_id}/sharing", { ...path(id), body: { sharing } })),
  );
}
