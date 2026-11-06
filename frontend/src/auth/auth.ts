import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Me = components["schemas"]["Me"];

export const ME_KEY = ["me"] as const;

/** The logged-in account, or null when not logged in. */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await unwrap(api.GET("/api/auth/me"));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      unwrap(api.POST("/api/auth/login", { body })),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSettled: () => {
      client.clear();
      client.setQueryData(ME_KEY, null);
    },
  });
}

/** USR-10: the account's language; null follows the browser. */
export function useSetLanguage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (language: string | null) =>
      unwrap(api.PUT("/api/auth/language", { body: { language } })),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  });
}

/** USR-11: the account's time zone; null follows the browser. */
export function useSetTimeZone() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (time_zone: string | null) =>
      unwrap(api.PUT("/api/auth/time-zone", { body: { time_zone } })),
    onSuccess: (me) => client.setQueryData(ME_KEY, me),
  });
}

export function useChangePassword() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      unwrap(api.POST("/api/auth/password", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ME_KEY }),
  });
}
