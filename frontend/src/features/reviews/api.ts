import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Review = components["schemas"]["ReviewOut"];
export type ReviewBrief = components["schemas"]["ReviewBrief"];

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

/** REV-01: the draft, or POL-20: the active version, reviewed again. */
export type ReviewTarget = "draft" | "active";

export interface StartReview {
  reviewerId: number;
  newsDays?: number; // REV-04
}

/** REV-01: one review of the whole draft: thesis and target structure. */
export function useStartReview(policyId: number, target: ReviewTarget = "draft") {
  const client = useQueryClient();
  const invalidate = useInvalidateOwners();
  return useMutation({
    mutationFn: ({ reviewerId, newsDays }: StartReview) => {
      const request = {
        params: { path: { policy_id: policyId } },
        body: { ai_reviewer_id: reviewerId, ...(newsDays && { news_days: newsDays }) },
      };
      return unwrap(
        target === "draft"
          ? api.POST("/api/policies/{policy_id}/draft/review", request)
          : api.POST("/api/policies/{policy_id}/active/review", request),
      );
    },
    onSuccess: (review) => {
      client.setQueryData(reviewKey(review.id), review);
      void client.invalidateQueries({ queryKey: usageKey });
      return invalidate();
    },
  });
}

/** REV-19: the review prompt of the draft as it is saved now; nothing is stored. */
export function useReviewPrompt(policyId: number, target: ReviewTarget = "draft") {
  return useMutation({
    mutationFn: ({ newsDays }: { newsDays?: number }) => {
      const request = {
        params: {
          path: { policy_id: policyId },
          query: newsDays ? { news_days: newsDays } : {},
        },
      };
      return unwrap(
        target === "draft"
          ? api.GET("/api/policies/{policy_id}/draft/review-prompt", request)
          : api.GET("/api/policies/{policy_id}/active/review-prompt", request),
      );
    },
  });
}

/** REV-18: stores the answer of an AI outside the app as the review of the draft. */
export function useSubmitManualReview(policyId: number, target: ReviewTarget = "draft") {
  const client = useQueryClient();
  const invalidate = useInvalidateOwners();
  return useMutation({
    mutationFn: (answer: string) => {
      const request = { params: { path: { policy_id: policyId } }, body: { answer } };
      return unwrap(
        target === "draft"
          ? api.POST("/api/policies/{policy_id}/draft/review/manual", request)
          : api.POST("/api/policies/{policy_id}/active/review/manual", request),
      );
    },
    onSuccess: (review) => {
      client.setQueryData(reviewKey(review.id), review);
      return invalidate();
    },
  });
}

export type Suggestion = Review["suggestions"][number];
export type SuggestionAction = "take-over" | "dismiss" | "undo";

/** REV-07, REV-22: takes over, dismisses or undoes a suggestion; returns the review and
 * the draft as they are now. */
export function useSuggestionAction(reviewId: number) {
  const client = useQueryClient();
  const invalidate = useInvalidateOwners();
  return useMutation({
    mutationFn: ({ action, suggestionId }: { action: SuggestionAction; suggestionId: number }) => {
      const params = { path: { review_id: reviewId, suggestion_id: suggestionId } };
      if (action === "take-over") {
        return unwrap(
          api.POST("/api/reviews/{review_id}/suggestions/{suggestion_id}/take-over", { params }),
        );
      }
      if (action === "dismiss") {
        return unwrap(
          api.POST("/api/reviews/{review_id}/suggestions/{suggestion_id}/dismiss", { params }),
        );
      }
      return unwrap(
        api.POST("/api/reviews/{review_id}/suggestions/{suggestion_id}/undo", { params }),
      );
    },
    onSuccess: (result) => {
      client.setQueryData(reviewKey(result.review.id), result.review);
      return invalidate();
    },
  });
}

export type ReviewLogEntry = components["schemas"]["ReviewLogEntry"];

/** REV-23: the saved reviews of a policy's versions, newest first. */
export function useReviewLog(policyId: number) {
  return useQuery({
    queryKey: ["policies", policyId, "reviews"],
    queryFn: () =>
      unwrap(
        api.GET("/api/policies/{policy_id}/reviews", {
          params: { path: { policy_id: policyId } },
        }),
      ),
  });
}
