import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type ThesisSummary = components["schemas"]["ThesisSummary"];
export type Thesis = components["schemas"]["ThesisOut"];
export type Revision = components["schemas"]["RevisionOut"];

export const thesesKey = ["theses"] as const;
const thesisKey = (id: number) => ["theses", id] as const;

export function useTheses() {
  return useQuery({ queryKey: thesesKey, queryFn: () => unwrap(api.GET("/api/theses")) });
}

export function useThesis(id: number) {
  return useQuery({
    queryKey: thesisKey(id),
    queryFn: () =>
      unwrap(api.GET("/api/theses/{thesis_id}", { params: { path: { thesis_id: id } } })),
  });
}

export function useRevision(thesisId: number, revisionNo: number | undefined) {
  return useQuery({
    queryKey: ["theses", thesisId, "revisions", revisionNo],
    enabled: revisionNo !== undefined,
    queryFn: () =>
      unwrap(
        api.GET("/api/theses/{thesis_id}/revisions/{revision_no}", {
          params: { path: { thesis_id: thesisId, revision_no: revisionNo! } },
        }),
      ),
  });
}

export function useRevisionDiff(thesisId: number, from: number, to: number) {
  return useQuery({
    queryKey: ["theses", thesisId, "diff", from, to],
    queryFn: () =>
      unwrap(
        api.GET("/api/theses/{thesis_id}/diff", {
          params: {
            path: { thesis_id: thesisId },
            query: { from_revision: from, to_revision: to },
          },
        }),
      ),
  });
}

function useInvalidateTheses() {
  const client = useQueryClient();
  // A draft change can confirm, outdate or delete its review (REV-09, REV-11)
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: thesesKey }),
      client.invalidateQueries({ queryKey: ["reviews"] }),
      client.invalidateQueries({ queryKey: ["timeline"] }),
    ]);
}

export function useCreateThesis() {
  const invalidate = useInvalidateTheses();
  return useMutation({
    mutationFn: (body: { title: string; content_md: string; visibility: string }) =>
      unwrap(api.POST("/api/theses", { body })),
    onSuccess: invalidate,
  });
}

export type DraftBody = {
  title: string;
  content_md: string;
  status: string;
  change_note?: string | null;
};

/** THS-02, THS-03: theses are edited in a draft that becomes a revision on activation. */
export function useThesisDraft(id: number) {
  const invalidate = useInvalidateTheses();
  const path = { params: { path: { thesis_id: id } } };
  return {
    create: useMutation({
      mutationFn: () => unwrap(api.POST("/api/theses/{thesis_id}/draft", path)),
      onSuccess: invalidate,
    }),
    save: useMutation({
      mutationFn: (body: DraftBody) =>
        unwrap(api.PUT("/api/theses/{thesis_id}/draft", { ...path, body })),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: () => unwrap(api.DELETE("/api/theses/{thesis_id}/draft", path)),
      onSuccess: invalidate,
    }),
    activate: useMutation({
      mutationFn: (changeNote: string | null) =>
        unwrap(
          api.POST("/api/theses/{thesis_id}/draft/activate", {
            ...path,
            body: { change_note: changeNote },
          }),
        ),
      onSuccess: invalidate,
    }),
  };
}

export function useSetVisibility(id: number) {
  const invalidate = useInvalidateTheses();
  return useMutation({
    mutationFn: (visibility: string) =>
      unwrap(
        api.PUT("/api/theses/{thesis_id}/visibility", {
          params: { path: { thesis_id: id } },
          body: { visibility },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useCopyThesis(id: number) {
  const invalidate = useInvalidateTheses();
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST("/api/theses/{thesis_id}/copy", { params: { path: { thesis_id: id } } })),
    onSuccess: invalidate,
  });
}

/** Raw import file as request body (IMP-01, IMP-07). */
function rawBody(text: string) {
  return { body: text as never, bodySerializer: (b: unknown) => b as string };
}

export const thesisImport = {
  preview: (text: string, thesisId?: number) =>
    thesisId === undefined
      ? unwrap(api.POST("/api/theses/import/preview", rawBody(text)))
      : unwrap(
          api.POST("/api/theses/{thesis_id}/import/preview", {
            params: { path: { thesis_id: thesisId } },
            ...rawBody(text),
          }),
        ),
  run: (text: string, thesisId?: number) =>
    thesisId === undefined
      ? unwrap(api.POST("/api/theses/import", rawBody(text)))
      : unwrap(
          api.POST("/api/theses/{thesis_id}/import", {
            params: { path: { thesis_id: thesisId } },
            ...rawBody(text),
          }),
        ),
};

export { rawBody };
