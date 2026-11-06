import { describe, expect, it } from "vitest";

import { sameVersion } from "./app-shell";

describe("version footer", () => {
  it("[NFR-09] treats a release candidate's -rc.N as the same version", () => {
    expect(sameVersion("1.2.0", "1.2.0")).toBe(true);
    expect(sameVersion("1.2.0", "1.2.0-rc.2")).toBe(true);
    expect(sameVersion("dev", "1.1.0+dev")).toBe(true);
    expect(sameVersion("1.2.0", "1.2.1")).toBe(false);
    expect(sameVersion("1.2.0", "1.2.0-beta")).toBe(false);
    expect(sameVersion("1.1.0+build.56", "1.1.0+build.57")).toBe(false);
  });
});
