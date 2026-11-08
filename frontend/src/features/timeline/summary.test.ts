import { afterEach, describe, expect, it } from "vitest";

import { applyLanguage } from "@/i18n";

import type { TimelineEvent } from "./api";
import { eventSummary } from "./summary";

function event(
  type: string,
  params: Record<string, unknown> | null,
  summary = "stored",
): TimelineEvent {
  return {
    id: 1,
    occurred_at: "2026-11-03T10:00:00+00:00",
    type,
    summary,
    params,
    portfolio_id: null,
    policy_version_id: null,
    rebalance_id: null,
    review_id: null,
  };
}

// The same values as in the backend tests, with the backend's English sentence
const EXAMPLES: [TimelineEvent, string, string][] = [
  [
    event("policy_activated", {
      version: "core-v2",
      portfolios: ["Main", "Other"],
      note: "growth change",
    }),
    "core-v2 activated (Main, Other): growth change",
    "core-v2 aktiviert (Main, Other): growth change",
  ],
  [
    event("policy_activated", { version: "core-v1", portfolios: [], note: null }),
    "core-v1 activated (no portfolios)",
    "core-v1 aktiviert (keine Portfolios)",
  ],
  [
    event("portfolio_assigned", {
      portfolio: "Main",
      policy: "core",
      version: "core-v1",
      created: true,
    }),
    "Portfolio Main created with policy core (core-v1)",
    "Portfolio Main mit der Anlagestrategie core (core-v1) erstellt",
  ],
  [
    event("portfolio_assigned", {
      portfolio: "Main",
      policy: "growth",
      version: "growth-v1",
      created: false,
    }),
    "Portfolio Main reassigned to policy growth (growth-v1)",
    "Portfolio Main der Anlagestrategie growth (growth-v1) zugewiesen",
  ],
  [
    event("rebalance_confirmed", {
      portfolio: "Main",
      sold: "190",
      bought: "2718.4",
      withdrawal: "200",
      precise: false,
    }),
    "Main: rebalanced, sold 190, bought 2,718, withdrew 200",
    "Main: Rebalancing, verkauft 190, gekauft 2’718, entnommen 200",
  ],
  [
    event("thesis_review_confirmed", {
      title: "Core thesis",
      revision: 2,
      verdict: "needs_adaptation",
      total: 7,
      modified: true,
    }),
    // REV-06: verdicts from before scoring version 3 are shown as their semaphore
    "Thesis review of 'Core thesis' revision 2: warning, 7 / 10, modified",
    "Prüfung der Anlagethese «Core thesis» Revision 2: Warnung, 7 / 10, geändert",
  ],
  [
    event("thesis_review_confirmed", { version: "core-v3", verdict: "broken", total: 4.5 }),
    "Thesis review of core-v3: broken, 4.5 / 10",
    "Prüfung der Anlagethese von core-v3: gebrochen, 4.5 / 10",
  ],
  [
    event("policy_review_confirmed", {
      version: "core-v2",
      verdict: null,
      total: 7.5,
      modified: false,
    }),
    "Policy review of core-v2: 7.5 / 10",
    "Prüfung der Anlagestrategie core-v2: 7.5 / 10",
  ],
  [
    event("review_confirmed", { version: "core-v4", verdict: "warning", total: 6.5 }),
    "Review of core-v4: warning, 6.5 / 10",
    "Prüfung von core-v4: Warnung, 6.5 / 10",
  ],
  [
    event("review_confirmed", { version: "core-v5", verdict: "good", total: 8 }),
    "Review of core-v5: good, 8 / 10",
    "Prüfung von core-v5: gut, 8 / 10",
  ],
  [
    // REV-12, POL-20: a review of the active version saved later
    event("review_saved", { version: "core-v5", verdict: "warning", total: 6.5, method: "ai" }),
    "Review of core-v5 (again): warning, 6.5 / 10",
    "Prüfung von core-v5 (erneut): Warnung, 6.5 / 10",
  ],
  [
    event("thesis_revised", { title: "Growth", revision: 3, version: "core-v1", used_revision: 2 }),
    "Thesis 'Growth' has a new revision 3 (policy core-v1 uses revision 2)",
    "Anlagethese «Growth» hat eine neue Revision 3 (Anlagestrategie core-v1 verwendet Revision 2)",
  ],
];

/** Node's ICU writes the Swiss thousands separator as ', browsers as ’. */
const swiss = (text: string) => text.replace(/'(?=\d{3})/g, "’");

describe("timeline summaries", () => {
  afterEach(() => applyLanguage("en"));

  it("[TL-02] [NFR-10] [REV-12] writes each entry like the backend in English", () => {
    applyLanguage("en");
    for (const [e, english] of EXAMPLES) expect(eventSummary(e), e.type).toBe(english);
  });

  it("[TL-02] [NFR-10] writes each entry in German with de-CH numbers", () => {
    applyLanguage("de");
    for (const [e, , german] of EXAMPLES) expect(swiss(eventSummary(e)), e.type).toBe(german);
  });

  it("[TL-02] keeps the stored English summary of older entries and unknown types", () => {
    applyLanguage("de");
    expect(eventSummary(event("policy_activated", null, "core-v1 activated"))).toBe(
      "core-v1 activated",
    );
    expect(eventSummary(event("something_new", { x: 1 }, "Something new"))).toBe("Something new");
  });
});
