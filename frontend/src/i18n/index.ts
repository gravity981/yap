import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { de } from "./de";
import { en } from "./en";

// UI languages (NFR-10, USR-10); the backend accepts the same codes
export const LANGUAGES = ["en", "de"] as const;
export type Language = (typeof LANGUAGES)[number];

/** Number and date formats per language; German is written for Switzerland (de-CH). */
const LOCALES: Record<Language, string | undefined> = {
  en: undefined, // the browser's own locale
  de: "de-CH",
};

/** Before login and for accounts without a choice: German if the browser prefers it. */
export function browserLanguage(): Language {
  const preferred = navigator.languages?.[0] ?? navigator.language ?? "en";
  return preferred.toLowerCase().startsWith("de") ? "de" : "en";
}

export function currentLanguage(): Language {
  return i18n.language === "de" ? "de" : "en";
}

/** The locale for Intl formats of the current language. */
export function currentLocale(): string | undefined {
  return LOCALES[currentLanguage()];
}

/** Switches the UI; the account's choice, or the browser's language without one. */
export function applyLanguage(language: string | null | undefined): void {
  const next: Language = language === "de" || language === "en" ? language : browserLanguage();
  document.documentElement.lang = next === "de" ? "de-CH" : "en";
  if (i18n.language !== next) void i18n.changeLanguage(next);
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, de: { translation: de } },
  lng: browserLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
});

export default i18n;
