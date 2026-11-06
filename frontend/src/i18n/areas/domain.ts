import type { Messages } from "../messages";

// Labels of domain values used in several places: thesis status, review verdict, asset type.
export const en = {
  thesisStatus: {
    intact: "intact",
    needs_adaptation: "needs adaptation",
    broken: "broken",
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
  thesisStatus: {
    intact: "intakt",
    needs_adaptation: "Anpassung nötig",
    broken: "gebrochen",
  },
  assetType: {
    ETF: "ETF",
    stock: "Aktie",
    crypto: "Krypto",
    cash_buffer: "Liquiditätsreserve",
  },
};
