import type { Messages } from "../messages";

// Labels of domain values used in several places: semaphore (review verdict), asset type.
export const en = {
  semaphore: {
    good: "good",
    warning: "warning",
    broken: "broken",
    none: "not reviewed",
  },
  assetType: {
    ETF: "ETF",
    stock: "Stock",
    crypto: "Crypto",
    cash_buffer: "Cash buffer",
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  semaphore: {
    good: "gut",
    warning: "Warnung",
    broken: "gebrochen",
    none: "nicht geprüft",
  },
  assetType: {
    ETF: "ETF",
    stock: "Aktie",
    crypto: "Krypto",
    cash_buffer: "Liquiditätsreserve",
  },
};
