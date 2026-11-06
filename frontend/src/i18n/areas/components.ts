import type { Messages } from "../messages";

// Shared components: markdown editor, diff view, file import, forms, dialogs.
export const en = {
  stars: {
    outOf: "{{score}} of 10",
  },
  markdownEditor: {
    content: "Content",
    narrow: "{{label}} (narrow)",
    preview: "Preview",
    write: "Write",
    loading: "Loading editor …",
  },
  diff: {
    none: "No differences.",
    label: "Differences",
  },
  fileImport: {
    file: "Import file",
    cannotImport: "The file cannot be imported:",
    failed: "The import failed.",
    import: "Import",
  },
  form: {
    unexpected: "Something went wrong. Please try again.",
  },
  dialog: {
    close: "Close",
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  stars: {
    outOf: "{{score}} von 10",
  },
  markdownEditor: {
    content: "Inhalt",
    narrow: "{{label}} (schmal)",
    preview: "Vorschau",
    write: "Schreiben",
    loading: "Editor wird geladen …",
  },
  diff: {
    none: "Keine Unterschiede.",
    label: "Unterschiede",
  },
  fileImport: {
    file: "Importdatei",
    cannotImport: "Die Datei kann nicht importiert werden:",
    failed: "Der Import ist fehlgeschlagen.",
    import: "Importieren",
  },
  form: {
    unexpected: "Etwas ist schiefgelaufen. Bitte versuch es noch einmal.",
  },
  dialog: {
    close: "Schliessen",
  },
};
