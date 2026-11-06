import { describe, expect, it } from "vitest";

import {
  applyTimeZone,
  formatAmount,
  formatDate,
  formatDateTime,
  formatPct,
  formatPrice,
  formatUnits,
} from "./format";

describe("formatting", () => {
  it("[RB-15] rounds amounts to whole units unless precise amounts are on", () => {
    expect(formatAmount("1234.567", false, "en-US")).toBe("1,235");
    expect(formatAmount("1234.567", true, "en-US")).toBe("1,234.57");
  });

  it("[NFR-10] follows the locale for numbers", () => {
    expect(formatAmount("1234567.5", true, "de-DE")).toBe("1.234.567,50");
    expect(formatPct("55.123", "en-US")).toBe("55.1\u00a0%");
  });

  it("[NFR-14] shows UTC timestamps in the user's time zone", () => {
    const utc = "2026-07-01T10:00:00.000000+00:00";
    expect(formatDateTime(utc, "en-GB", "Europe/Zurich")).toBe("1 Jul 2026, 12:00");
    expect(formatDateTime(utc, "en-GB", "UTC")).toBe("1 Jul 2026, 10:00");
    expect(formatDate("2026-12-31T23:30:00+00:00", "en-GB", "Europe/Zurich")).toBe("1 Jan 2027");
  });

  it("[USR-11] uses the account's time zone unless one is given", () => {
    const utc = "2026-07-01T10:00:00+00:00";
    applyTimeZone("America/New_York");
    try {
      expect(formatDateTime(utc, "en-GB")).toBe("1 Jul 2026, 06:00");
      expect(formatDateTime(utc, "en-GB", "UTC")).toBe("1 Jul 2026, 10:00");
    } finally {
      applyTimeZone(null);
    }
  });

  it("[CMP-05] [NFR-04] shows units with every decimal and prices with enough decimals", () => {
    expect(formatUnits("12", "en-US")).toBe("12");
    expect(formatUnits("0.00000001", "en-US")).toBe("0.00000001"); // one satoshi
    // More digits than a JavaScript number holds: none is lost (ETH has 18 decimals)
    expect(formatUnits("123456789.123456789012345678", "en-US")).toBe(
      "123,456,789.123456789012345678",
    );
    // The Swiss thousands separator depends on the ICU version (’ or ')
    expect(formatUnits("1234.000000000000000001", "de-CH")).toMatch(/^1.234\.000000000000000001$/);
    expect(formatPrice("117.5", "en-US")).toBe("117.50");
    expect(formatPrice("61234.56789", "en-US")).toBe("61,234.5679");
    expect(formatPrice("0.5", "en-US")).toBe("0.50");
    expect(formatPrice("0.00001234", "en-US")).toBe("0.00001234");
  });
});
