import i18n from "i18next";
import createClient from "openapi-fetch";

import { formatDateTime } from "@/lib/format";

import type { paths } from "./schema";

type Params = Record<string, string | number>;

/** One problem of a validation error, with its path (IMP-06), in the UI language. */
export interface Problem {
  path: string;
  message: string;
  code?: string | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly problems: Problem[] = [],
    readonly code: string | null = null,
  ) {
    super(message);
  }
}

const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

/** NFR-10: a backend message in the UI language, by its code; the English text from the
 * server if the code is unknown (e.g. an older frontend). */
export function translateMessage(
  code: string | null | undefined,
  params: Params | undefined,
  fallback: string,
): string {
  const key = `errors.${code}`;
  if (!code || !i18n.exists(key)) return fallback;
  const values = Object.fromEntries(
    Object.entries(params ?? {}).map(([name, value]) => [
      name,
      typeof value === "string" && TIMESTAMP.test(value) ? formatDateTime(value) : value,
    ]),
  );
  return i18n.t(key as "errors.not_logged_in", values);
}

interface ErrorBody {
  detail?: unknown;
  code?: string | null;
  params?: Params;
  problems?: { path: string; message: string; code?: string | null; params?: Params }[];
}

// Same origin as the page; fetch is looked up per call so tests can replace it
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  credentials: "same-origin",
  fetch: (request: Request) => globalThis.fetch(request),
});

interface Result<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Returns the data of a call or throws an ApiError with the server's message. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const body = (error ?? {}) as ErrorBody;
    const detail = typeof body.detail === "string" ? body.detail : response.statusText;
    const problems = (body.problems ?? []).map((p) => ({
      path: p.path,
      message: translateMessage(p.code, p.params, p.message),
      code: p.code,
    }));
    throw new ApiError(
      response.status,
      translateMessage(body.code, body.params, detail),
      problems,
      body.code ?? null,
    );
  }
  return data as T;
}
