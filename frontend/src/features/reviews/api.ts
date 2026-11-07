import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Review = components["schemas"]["ReviewOut"];
export type ReviewBrief = components["schemas"]["ReviewBrief"];
export type ReviewKind = "thesis" | "policy";

const POLL_MS = 3000;
export const usageKey = ["reviews", "usage"] as const;
const reviewKey = (id: number) => ["reviews", id] as const;

export function isRunning(state: string | undefined) {
  return state === "queued" || state === "running";
}

/** Data that shows a review in short; refreshed when a review changes. */
function useInvalidateOwners() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ["theses"] }),
      client.invalidateQueries({ queryKey: ["policies"] }),
      client.invalidateQueries({ queryKey: ["timeline"] }),
    ]);
}

/** REV-08: polls while the review runs; the investor may leave the page meanwhile. */
export function useReview(id: number | undefined) {
  const invalidate = useInvalidateOwners();
  return useQuery({
    queryKey: reviewKey(id ?? 0),
    enabled: id !== undefined,
    queryFn: async () => {
      const review = await unwrap(
        api.GET("/api/reviews/{review_id}", { params: { path: { review_id: id! } } }),
      );
      if (!isRunning(review.state)) void invalidate();
      return review;
    },
    refetchInterval: (query) => (isRunning(query.state.data?.state) ? POLL_MS : false),
  });
}

/** REV-16: for the given AI reviewer, or the investor's default without one. */
export function useUsage(reviewerId?: number | null, enabled = true) {
  return useQuery({
    queryKey: [...usageKey, reviewerId ?? "default"],
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/reviews/usage", {
          params: { query: reviewerId ? { ai_reviewer_id: reviewerId } : {} },
        }),
      ),
  });
}

/** USR-08: the enabled AI reviewers an investor can choose from. */
export function useReviewerOptions() {
  return useQuery({
    queryKey: ["ai-reviewers"],
    queryFn: () => unwrap(api.GET("/api/ai-reviewers")),
  });
}

export interface StartReview {
  reviewerId: number;
  newsDays?: number; // thesis reviews only
}

export function useStartReview(kind: ReviewKind, ownerId: number) {
  const client = useQueryClient();
  const invalidate = useInvalidateOwners();
  return useMutation({
    mutationFn: ({ reviewerId, newsDays }: StartReview) =>
      kind === "thesis"
        ? unwrap(
            api.POST("/api/theses/{thesis_id}/draft/review", {
              params: { path: { thesis_id: ownerId } },
              body: { ai_reviewer_id: reviewerId, ...(newsDays && { news_days: newsDays }) },
            }),
          )
        : unwrap(
            api.POST("/api/policies/{policy_id}/draft/review", {
              params: { path: { policy_id: ownerId } },
              body: { ai_reviewer_id: reviewerId },
            }),
          ),
    onSuccess: (review) => {
      client.setQueryData(reviewKey(review.id), review);
      void client.invalidateQueries({ queryKey: usageKey });
      return invalidate();
    },
  });
}
