import { afterEach, describe, expect, it, vi } from "vitest";

import { de } from "./de";
import { en } from "./en";
import i18n, { applyLanguage, browserLanguage, currentLocale } from "./index";
import { formatAmount, formatDate, formatPct } from "@/lib/format";

/** All keys of a nested message object, e.g. "nav.dashboard". */
function keys(messages: object, prefix = ""): string[] {
  return Object.entries(messages).flatMap(([key, value]) =>
    typeof value === "string" ? [`${prefix}${key}`] : keys(value, `${prefix}${key}.`),
  );
}

/** The {{placeholders}} of a text, sorted. */
function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]!).sort();
}

function lookup(messages: object, key: string): string {
  return key.split(".").reduce<any>((node, part) => node[part], messages); // eslint-disable-line @typescript-eslint/no-explicit-any
}

describe("i18n", () => {
  afterEach(() => {
    applyLanguage("en");
    vi.unstubAllGlobals();
  });

  it("[NFR-10] has the same keys and placeholders in English and German", () => {
    expect(keys(de).sort()).toEqual(keys(en).sort());
    for (const key of keys(en)) {
      expect(placeholders(lookup(de, key)), key).toEqual(placeholders(lookup(en, key)));
      expect(lookup(de, key).trim(), key).not.toBe("");
    }
  });

  it("[NFR-10] writes German in Swiss spelling", () => {
    for (const key of keys(de)) expect(lookup(de, key), key).not.toContain("ß");
  });

  it("[USR-10] starts in the browser's language", () => {
    vi.stubGlobal("navigator", { ...navigator, languages: ["de-CH", "en"] });
    expect(browserLanguage()).toBe("de");
    vi.stubGlobal("navigator", { ...navigator, languages: ["fr-CH", "de"] });
    expect(browserLanguage()).toBe("en");
  });

  it("[USR-10] [NFR-10] switches texts and formats; German uses de-CH", () => {
    applyLanguage("de");
    expect(i18n.t("nav.dashboard")).toBe("Übersicht");
    expect(document.documentElement.lang).toBe("de-CH");
    expect(currentLocale()).toBe("de-CH");
    // Browsers write the Swiss thousands separator as ’, Node's ICU as '
    expect(formatAmount("1234.5", true)).toMatch(/^1['’]234\.50$/);
    expect(formatPct("12.34")).toBe("12.3\u00a0%");
    expect(formatDate("2026-11-02T10:00:00+00:00", undefined, "UTC")).toBe("02.11.2026");
    applyLanguage("en");
    expect(i18n.t("nav.dashboard")).toBe("Dashboard");
  });
});
