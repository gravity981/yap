import type { Messages } from "../messages";

// AI reviews: start, result, score course (features/reviews).
export const en = {
  section: {
    thesis: "Thesis review",
    policy: "Policy review",
    notReviewed: "Not reviewed.",
  },
  start: {
    dataThesis:
      "To run it, the thesis text is sent to the provider of your AI reviewer, which searches the web for news. ",
    dataPolicy:
      "To run it, the thesis text and the target structure (percentages, thresholds, exit flags, rationales) are sent to the provider of your AI reviewer. ",
    dataNothingElse: "No amounts, portfolios or personal data are sent.",
    default: " (default)",
    newsDays: "News of the last … days",
    button: "Start review",
    again: "Run review again",
    usage: "{{used}} of {{limit}} reviews with {{name}} used this month",
  },
  result: {
    running:
      "The review is running (started {{started}}). This takes a few minutes; you can leave the page meanwhile.",
    failed: "The review failed: {{error}}",
    confirmed: "confirmed",
    notConfirmed: "not confirmed yet",
    outdated: "outdated: the draft changed since",
    manual: "manual review with {{model}}",
    scoring: "scoring v{{version}}",
    news: "news {{from}} – {{to}}",
    notAdvice:
      "AI reviews can be wrong or incomplete, and are not financial advice. You decide what to change.",
  },
  score: {
    totalLabel: "Total score",
    outOf: "{{score}} / 10",
  },
  pane: {
    noReview: "This draft has no review yet; it needs one to be activated.",
    method: "Review method",
    manual: "Manual (an AI of your choice)",
    defaultIn: "The default method is set in your <goto>settings</goto>.",
    dataThesis:
      "The prompt contains the review instructions and the thesis text, nothing else: no amounts, portfolios or personal data. You decide where to paste it.",
    dataPolicy:
      "The prompt contains the review instructions, the thesis text and the target structure (percentages, thresholds, exit flags, rationales), nothing else: no amounts, portfolios or personal data. You decide where to paste it.",
    copy: "Copy review prompt",
    copied: "Copied. Paste it into your AI, then paste its whole answer below.",
    copyFailed: "Your browser did not allow copying; copy the prompt from here",
    manualForm: "Manual review",
    model: "AI model used",
    modelPlaceholder: "e.g. ChatGPT 5",
    answer: "Answer of the AI",
    problems: "The answer cannot be used:",
    save: "Save review",
    tab: "Review",
    inEditor: "Review the draft in the <goto>editor</goto>.",
  },
  legacy: {
    title: "You changed this result when reviews could still be changed:",
    verdict: "Your verdict: {{verdict}}",
    score: "{{name}}: {{score}}",
    note: "Why: {{note}}",
  },
  // Scoring version 2: the sections of the thesis template (THS-07)
  aspects: {
    T1: "Belief",
    T2: "Fit and implementation",
    T3: "Opportunity",
    T4: "Downside",
    T5: "Invalidation, warnings and monitoring",
    T6: "Current evidence",
    P1: "Coverage",
    P2: "Weighting",
    P3: "Bands",
    P4: "Exits",
    P5: "Concentration",
    P6: "Rationales",
  },
  // Scoring version 1: thesis aspects of reviews before the template of THS-07
  aspectsV1: {
    T1: "Core claim",
    T2: "Value drivers",
    T3: "Risks",
    T4: "Break conditions and warning signals",
    T5: "Fit and alternatives",
    T6: "Current evidence",
  },
  sources: "Sources",
  suggestions: {
    title: "Suggestions",
    note: "Nothing is changed automatically; take over what you agree with into the draft.",
    thesis_text: "Thesis text",
    thesis_status: "Thesis status",
    policy_position: "Position",
  },
  states: {
    queued: "queued",
    running: "running",
    done: "done",
    failed: "failed",
  },
  brief: {
    state: "review {{state}}",
    label: "Review",
  },
  activation: {
    noReview: "This draft has no review. Activate it anyway?",
    outdated: "The draft changed after its review. Activate it with the outdated review?",
  },
  course: {
    label: "Review score over the revisions",
    caption: "Total review score per revision",
    point: "{{label}}: {{score}} of 10",
    tooltip: ": {{score}} / 10",
    tick: "r{{no}}",
    version: "v{{version}}",
    versionNote:
      "The scoring changed in between (dashed line); scores before and after are not directly comparable.",
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  section: {
    thesis: "Prüfung der Anlagethese",
    policy: "Prüfung der Anlagestrategie",
    notReviewed: "Nicht geprüft.",
  },
  start: {
    dataThesis:
      "Dafür wird der Text der Anlagethese an den Anbieter deines KI-Reviewers gesendet, der im Web nach Nachrichten sucht. ",
    dataPolicy:
      "Dafür werden der Text der Anlagethese und die Zielstruktur (Anteile, Schwellen, Exit-Markierungen, Begründungen) an den Anbieter deines KI-Reviewers gesendet. ",
    dataNothingElse: "Es werden keine Beträge, Portfolios oder persönlichen Daten gesendet.",
    default: " (Standard)",
    newsDays: "Nachrichten der letzten … Tage",
    button: "Prüfung starten",
    again: "Prüfung erneut ausführen",
    usage: "{{used}} von {{limit}} Prüfungen mit {{name}} in diesem Monat verwendet",
  },
  result: {
    running:
      "Die Prüfung läuft (gestartet {{started}}). Das dauert einige Minuten; du kannst die Seite inzwischen verlassen.",
    failed: "Die Prüfung ist fehlgeschlagen: {{error}}",
    confirmed: "bestätigt",
    notConfirmed: "noch nicht bestätigt",
    outdated: "veraltet: der Entwurf wurde seither geändert",
    manual: "manuelle Prüfung mit {{model}}",
    scoring: "Bewertung v{{version}}",
    news: "Nachrichten {{from}} – {{to}}",
    notAdvice:
      "KI-Prüfungen können falsch oder unvollständig sein und sind keine Finanzberatung. Du entscheidest, was du änderst.",
  },
  score: {
    totalLabel: "Gesamtbewertung",
    outOf: "{{score}} / 10",
  },
  pane: {
    noReview: "Dieser Entwurf hat noch keine Prüfung; zum Aktivieren braucht er eine.",
    method: "Prüfmethode",
    manual: "Manuell (eine KI deiner Wahl)",
    defaultIn: "Die Standard-Prüfmethode legst du in deinen <goto>Einstellungen</goto> fest.",
    dataThesis:
      "Der Prompt enthält die Prüfanweisungen und den Text der Anlagethese, sonst nichts: keine Beträge, Portfolios oder persönlichen Daten. Du entscheidest, wo du ihn einfügst.",
    dataPolicy:
      "Der Prompt enthält die Prüfanweisungen, den Text der Anlagethese und die Zielstruktur (Anteile, Schwellen, Exit-Markierungen, Begründungen), sonst nichts: keine Beträge, Portfolios oder persönlichen Daten. Du entscheidest, wo du ihn einfügst.",
    copy: "Prüf-Prompt kopieren",
    copied: "Kopiert. Füge ihn in deine KI ein und füge danach ihre ganze Antwort unten ein.",
    copyFailed: "Dein Browser hat das Kopieren nicht erlaubt; kopiere den Prompt von hier",
    manualForm: "Manuelle Prüfung",
    model: "Verwendetes KI-Modell",
    modelPlaceholder: "z. B. ChatGPT 5",
    answer: "Antwort der KI",
    problems: "Die Antwort kann nicht verwendet werden:",
    save: "Prüfung speichern",
    tab: "Prüfung",
    inEditor: "Prüfe den Entwurf im <goto>Editor</goto>.",
  },
  legacy: {
    title: "Du hast dieses Ergebnis geändert, als Prüfungen noch geändert werden konnten:",
    verdict: "Dein Urteil: {{verdict}}",
    score: "{{name}}: {{score}}",
    note: "Warum: {{note}}",
  },
  aspects: {
    T1: "Überzeugung",
    T2: "Eignung und Umsetzung",
    T3: "Chancen",
    T4: "Risiken",
    T5: "Widerlegung, Frühwarnungen und Überwachung",
    T6: "Aktuelle Belege",
    P1: "Abdeckung",
    P2: "Gewichtung",
    P3: "Bänder",
    P4: "Exits",
    P5: "Konzentration",
    P6: "Begründungen",
  },
  aspectsV1: {
    T1: "Kernaussage",
    T2: "Werttreiber",
    T3: "Risiken",
    T4: "Bruchbedingungen und Warnsignale",
    T5: "Eignung und Alternativen",
    T6: "Aktuelle Belege",
  },
  sources: "Quellen",
  suggestions: {
    title: "Vorschläge",
    note: "Nichts wird automatisch geändert; übernimm in den Entwurf, was du für richtig hältst.",
    thesis_text: "Text der Anlagethese",
    thesis_status: "Status der Anlagethese",
    policy_position: "Position",
  },
  states: {
    queued: "wartet",
    running: "läuft",
    done: "fertig",
    failed: "fehlgeschlagen",
  },
  brief: {
    state: "Prüfung {{state}}",
    label: "Prüfung",
  },
  activation: {
    noReview: "Dieser Entwurf hat keine Prüfung. Trotzdem aktivieren?",
    outdated:
      "Der Entwurf wurde nach seiner Prüfung geändert. Mit der veralteten Prüfung aktivieren?",
  },
  course: {
    label: "Bewertung der Prüfungen über die Revisionen",
    caption: "Gesamtbewertung der Prüfung pro Revision",
    point: "{{label}}: {{score}} von 10",
    tooltip: ": {{score}} / 10",
    tick: "r{{no}}",
    version: "v{{version}}",
    versionNote:
      "Die Bewertung hat sich dazwischen geändert (gestrichelte Linie); Bewertungen davor und danach sind nicht direkt vergleichbar.",
  },
};
