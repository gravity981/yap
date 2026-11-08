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
import type { en } from "./en";
import type { Messages } from "./messages";

// German texts in Swiss spelling, addressing the user with "du"; terms in README.md (NFR-10)
export const de: Messages<typeof en> = {
  domain: domain.de,
  errors: errors.de,
  components: components.de,
  theses: theses.de,
  policies: policies.de,
  portfolios: portfolios.de,
  rebalance: rebalance.de,
  reviews: reviews.de,
  timeline: timeline.de,
  pages: pages.de,
  prices: prices.de,

  common: {
    save: "Speichern",
    saved: "Gespeichert.",
    cancel: "Abbrechen",
    loading: "Wird geladen …",
    notFound: "Nicht gefunden.",
  },
  nav: {
    main: "Hauptnavigation",
    dashboard: "Übersicht",
    portfolios: "Portfolios",
    policies: "Anlagestrategien",
    timeline: "Verlauf",
    administration: "Verwaltung",
    accounts: "Konten",
    aiReviewers: "KI-Reviewer",
    priceProviders: "Preisanbieter",
    openMenu: "Menü öffnen",
    menu: "Menü",
  },
  userMenu: {
    theme: "Darstellung",
    themeSystem: "System",
    themeLight: "Hell",
    themeDark: "Dunkel",
    settings: "Einstellungen",
    changePassword: "Passwort ändern",
    logOut: "Abmelden",
  },
  footer: {
    version: "Version {{version}}",
    serverDiffers: " (Server {{version}}; Seite neu laden)",
    commit: "Commit {{commit}}",
    sourceCode: "Quellcode",
    license: "Lizenz (AGPL-3.0)",
    thirdPartyLicenses: "Lizenzen von Drittanbietern",
  },
  notAdvice: {
    label: "Keine Finanzberatung",
    short: "Keine Finanzberatung.",
    long: "Keine Finanzberatung. Dieses Werkzeug wendet deine eigenen Regeln an und hält deine Entscheidungen fest; es gibt keine Anlage-, Rechts- oder Steuerberatung. KI-Prüfungen können falsch oder unvollständig sein. Du entscheidest und handelst auf eigenes Risiko.",
  },
  settings: {
    title: "Einstellungen",
    description: "Deine eigenen Einstellungen.",
    language: {
      title: "Sprache",
      description:
        "Die Sprache der App für dein Konto, auf jedem Gerät. Zahlen und Daten richten sich ebenfalls danach.",
      label: "Sprache",
      browser: "Wie der Browser",
      en: "English",
      de: "Deutsch",
    },
    timeZone: {
      title: "Zeitzone",
      description:
        "Daten und Zeiten werden für dein Konto auf jedem Gerät in dieser Zeitzone angezeigt, und Zeiten, die du eingibst, gelten in ihr.",
      label: "Zeitzone",
      browser: "Wie der Browser ({{zone}})",
    },
    reviewer: {
      title: "Standard-Prüfmethode",
      description:
        "Was vorausgewählt ist, wenn du den Entwurf einer Anlagethese oder Anlagestrategie prüfst; für jede Prüfung kannst du eine andere wählen. Jeder KI-Reviewer hat sein eigenes Monatslimit, das der Admin festlegt.",
      usage: "{{used}} von {{limit}} Prüfungen mit {{name}} in diesem Monat verwendet.",
      gone: "Dein Standard-KI-Reviewer ist nicht mehr verfügbar; wähle einen anderen.",
      none: "Es gibt noch keine KI-Reviewer; du kannst trotzdem manuell prüfen.",
      manual: "Manuell",
      manualDescription:
        "Du kopierst den Prüf-Prompt in eine KI deiner Wahl und fügst ihre Antwort wieder ein. Zählt für kein Limit.",
      perMonth: "{{provider}} {{model}} · {{limit}} Prüfungen pro Monat",
    },
  },
};
