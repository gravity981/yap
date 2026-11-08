import { describe, expect, it } from "vitest";

import { THESIS_TEMPLATES } from "./template";

describe("thesis template", () => {
  it("[THS-07] has the same sections in both languages, matching the review aspects", () => {
    const structure = (template: string) =>
      template
        .split("\n")
        .map((line) =>
          line.startsWith("## ") ? line.slice(0, 5) : line.startsWith("- ") ? "-" : null,
        )
        .filter(Boolean);
    expect(structure(THESIS_TEMPLATES.de)).toEqual(structure(THESIS_TEMPLATES.en));
    const headings = THESIS_TEMPLATES.en.split("\n").filter((l) => l.startsWith("## "));
    expect(headings.map((h) => h.split(" — ")[0])).toEqual([
      "## 1. Belief",
      "## 2. Investor Fit",
      "## 3. Implementation",
      "## 4. Opportunity",
      "## 5. Downside",
      "## 6. Invalidation",
      "## 7. Early Warnings",
      "## 8. Monitoring",
    ]);
    for (const template of Object.values(THESIS_TEMPLATES)) {
      expect(template).not.toMatch(/ß/); // Swiss spelling
    }
  });
});
