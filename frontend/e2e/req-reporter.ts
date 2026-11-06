// Writes {requirement ID: [{test, outcome}]} for the requirement coverage report
// (test strategy §3), from requirement IDs in test titles: "[RB-16] ...".
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { Reporter, TestCase, TestResult } from "@playwright/test/reporter";

const REQ_ID = /\[([A-Z]{2,4}-\d{2})\]/g;
const here = dirname(fileURLToPath(import.meta.url));
const resultsDir = process.env.REQ_RESULTS_DIR ?? resolve(here, "../../backend/.req-results");

export default class RequirementReporter implements Reporter {
  private results: Record<string, { test: string; outcome: string }[]> = {};

  onTestEnd(test: TestCase, result: TestResult) {
    const title = test.titlePath().join(" › ");
    const outcome = result.status === "passed" ? "passed" : "failed";
    for (const [, id] of title.matchAll(REQ_ID)) {
      // a retry replaces the earlier result of the same test
      const list = (this.results[id!] ??= []).filter((r) => r.test !== title);
      list.push({ test: title, outcome });
      this.results[id!] = list;
    }
  }

  onEnd() {
    mkdirSync(resultsDir, { recursive: true });
    writeFileSync(resolve(resultsDir, "playwright.json"), JSON.stringify(this.results, null, 2));
  }
}
