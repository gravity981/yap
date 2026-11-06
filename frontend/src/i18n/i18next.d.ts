import "i18next";

import type { en } from "./en";

// Typed keys: t("nav.dashboard") is checked by tsc, a typo fails the build (NFR-10)
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: { translation: typeof en };
  }
}
