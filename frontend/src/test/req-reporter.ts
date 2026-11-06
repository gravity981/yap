// Writes {requirement ID: [{test, outcome}]} for the requirement coverage report
// (test strategy §3). Requirement IDs are taken from test names: "[CMP-05] ...".
// Only a full run writes the file, so a filtered run cannot hide missing tests.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { Reporter, TestModule } from "vitest/node";

const REQ_ID = /\[([A-Z]{2,4}-\d{2})\]/g;
const here = dirname(fileURLToPath(import.meta.url));
const resultsDir = process.env.REQ_RESULTS_DIR ?? resolve(here, "../../../backend/.req-results");

function fullRun(): boolean {
  const args = process.argv.slice(2).filter((a) => a !== "run");
  return args.every((a) => a.startsWith("--") && !a.startsWith("--testNamePattern"));
}

export default class RequirementReporter implements Reporter {
  onTestRunEnd(testModules: ReadonlyArray<TestModule>) {
    if (!fullRun()) return;
    const results: Record<string, { test: string; outcome: string }[]> = {};
    for (const module of testModules) {
      for (const test of module.children.allTests()) {
        const outcome = test.result().state === "passed" ? "passed" : "failed";
        for (const [, id] of test.fullName.matchAll(REQ_ID)) {
          (results[id!] ??= []).push({ test: `${module.moduleId}::${test.fullName}`, outcome });
        }
      }
    }
    mkdirSync(resultsDir, { recursive: true });
    writeFileSync(resolve(resultsDir, "vitest.json"), JSON.stringify(results, null, 2));
  }
}
