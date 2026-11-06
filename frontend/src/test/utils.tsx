import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { vi } from "vitest";

import { ThemeProvider } from "@/lib/theme";
import { createAppRouter } from "@/router";

export type Handler = (request: Request, body: unknown) => Response | Promise<Response>;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Replaces fetch; handlers are keyed by "METHOD /path" (without query). */
export function mockApi(handlers: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const url = new URL(request.url);
      const key = `${request.method} ${url.pathname}`;
      const text = await request.text();
      const body = text ? JSON.parse(text) : undefined;
      calls.push({ method: request.method, path: url.pathname + url.search, body });
      const handler = handlers[key];
      if (!handler) return json({ detail: `No mock for ${key}` }, 404);
      return handler(request, body);
    }),
  );
  return calls;
}

export const investor = {
  id: 1,
  username: "alice",
  is_admin: false,
  is_investor: true,
  base_currency: "CHF",
  ai_reviewer_id: 1,
  language: null,
  time_zone: null,
  must_change_password: false,
};
export const admin = {
  ...investor,
  id: 9,
  username: "root",
  is_admin: true,
  is_investor: false,
  base_currency: null,
  ai_reviewer_id: null,
};
/** USR-09: admin and investor in one account. */
export const adminInvestor = {
  ...investor,
  id: 8,
  username: "owner",
  is_admin: true,
};

/** Renders the whole app at `path` with fresh query and router state. */
export function renderApp(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const utils = render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...utils, router, queryClient };
}
