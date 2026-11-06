import { afterEach, describe, expect, it } from "vitest";

import { applyLanguage } from "@/i18n";
import { json } from "@/test/utils";

import { ApiError, translateMessage, unwrap } from "./client";

function failing(status: number, body: unknown) {
  return Promise.resolve({ error: body, response: json(body, status) });
}

async function error(status: number, body: unknown): Promise<ApiError> {
  try {
    await unwrap(failing(status, body));
  } catch (e) {
    return e as ApiError;
  }
  throw new Error("no error");
}

describe("backend messages", () => {
  afterEach(() => applyLanguage("en"));

  it("[NFR-10] shows a backend message in the UI language by its code", async () => {
    applyLanguage("de");
    const e = await error(404, {
      detail: "Thesis 9 not found",
      code: "thesis_not_found",
      params: { id: 9 },
    });
    expect(e.message).toBe("Anlagethese 9 nicht gefunden");
    expect([e.status, e.code]).toEqual([404, "thesis_not_found"]);
    applyLanguage("en");
    const english = await error(404, {
      detail: "Thesis 9 not found",
      code: "thesis_not_found",
      params: { id: 9 },
    });
    expect(english.message).toBe("Thesis 9 not found");
  });

  it("[NFR-10] translates the problems of a validation error too", async () => {
    applyLanguage("de");
    const e = await error(422, {
      detail: "x",
      code: "invalid_input",
      params: {},
      problems: [
        { path: "name", message: "The input is invalid", code: "invalid_input", params: {} },
      ],
    });
    expect(e.problems).toEqual([
      { path: "name", message: "Die Eingabe ist ungültig", code: "invalid_input" },
    ]);
  });

  it("[NFR-10] keeps the server's text for unknown codes and old servers", async () => {
    applyLanguage("de");
    expect((await error(409, { detail: "Something new", code: "brand_new_code" })).message).toBe(
      "Something new",
    );
    expect((await error(409, { detail: "Without code" })).message).toBe("Without code");
    expect(translateMessage(null, undefined, "fallback")).toBe("fallback");
  });

  it("[NFR-10] formats timestamps in the parameters in the UI language", async () => {
    applyLanguage("de");
    const e = await error(429, {
      detail: "Too many failed logins; try again after 2026-11-03T10:15:00+00:00",
      code: "login_locked",
      params: { until: "2026-11-03T10:15:00+00:00" },
    });
    expect(e.message).not.toContain("2026-11-03T");
    expect(e.message).toMatch(/03\.11\.2026/);
  });
});
