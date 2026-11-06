// English UI texts (NFR-10): app-wide ones here, those of a feature in areas/<area>.ts.
// The German ones (de.ts) must have exactly the same keys; the types and
// src/i18n/i18n.test.ts check that.

import * as domain from "./areas/domain";
import * as errors from "./areas/errors";
import * as components from "./areas/components";
import * as theses from "./areas/theses";
import * as policies from "./areas/policies";
import * as portfolios from "./areas/portfolios";
import * as rebalance from "./areas/rebalance";
import * as reviews from "./areas/reviews";
import * as timeline from "./areas/timeline";
import * as pages from "./areas/pages";
import * as prices from "./areas/prices";

export const en = {
  domain: domain.en,
  errors: errors.en,
  components: components.en,
  theses: theses.en,
  policies: policies.en,
  portfolios: portfolios.en,
  rebalance: rebalance.en,
  reviews: reviews.en,
  timeline: timeline.en,
  pages: pages.en,
  prices: prices.en,

  common: {
    save: "Save",
    saved: "Saved.",
    cancel: "Cancel",
    loading: "Loading …",
    notFound: "Not found.",
  },
  nav: {
    main: "Main",
    dashboard: "Dashboard",
    portfolios: "Portfolios",
    policies: "Policies",
    theses: "Theses",
    timeline: "Timeline",
    administration: "Administration",
    accounts: "Accounts",
    aiReviewers: "AI reviewers",
    priceProviders: "Price providers",
    openMenu: "Open menu",
    menu: "Menu",
  },
  userMenu: {
    theme: "Theme",
    themeSystem: "System",
    themeLight: "Light",
    themeDark: "Dark",
    settings: "Settings",
    changePassword: "Change password",
    logOut: "Log out",
  },
  footer: {
    version: "Version {{version}}",
    serverDiffers: " (server {{version}}; reload the page)",
    commit: "commit {{commit}}",
    sourceCode: "Source code",
    license: "License (AGPL-3.0)",
    thirdPartyLicenses: "Third-party licenses",
  },
  notAdvice: {
    label: "Not financial advice",
    short: "Not financial advice.",
    long: "Not financial advice. This tool applies your own rules and records your decisions; it gives no investment, legal or tax advice. AI reviews can be wrong or incomplete. You decide and act at your own risk.",
  },
  settings: {
    title: "Settings",
    description: "Your own settings.",
    language: {
      title: "Language",
      description:
        "The language of the app for your account, on every device. Numbers and dates follow it as well.",
      label: "Language",
      browser: "Like the browser",
      en: "English",
      de: "Deutsch",
    },
    timeZone: {
      title: "Time zone",
      description:
        "Dates and times are shown in this time zone for your account, on every device, and times you enter are read in it.",
      label: "Time zone",
      browser: "Like the browser ({{zone}})",
    },
    reviewer: {
      title: "Default AI reviewer",
      description:
        "The AI that is preselected when you start a thesis or policy review; you can choose another one for each review. Each reviewer has its own monthly limit, set by the admin.",
      usage: "{{used}} of {{limit}} reviews with {{name}} used this month.",
      gone: "Your default AI reviewer is no longer available; choose another one.",
      none: "There are no AI reviewers yet, so reviews are not available. Ask the admin.",
      perMonth: "{{provider}} {{model}} · {{limit}} reviews per month",
    },
  },
};
