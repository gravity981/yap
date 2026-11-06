import type { Messages } from "../messages";

// AI reviews: start, result, modify, score course (features/reviews).
export const en = {
  section: {
    thesis: "Thesis review",
    policy: "Policy review",
    notReviewed: "Not reviewed.",
  },
  start: {
    form: "Start review",
    introThesis:
      "An AI judges the thesis on six aspects and checks it against current news. The result is confirmed when you activate the draft; you can change it before.",
    introPolicy:
      "An AI judges how well the target structure matches the thesis, on six aspects. The result is confirmed when you activate the draft; you can change it before.",
    dataThesis:
      "To run it, the thesis text is sent to the provider of your AI reviewer, which searches the web for news. ",
    dataPolicy:
      "To run it, the thesis text and the target structure (percentages, thresholds, exit flags, rationales) are sent to the provider of your AI reviewer. ",
    dataNothingElse: "No amounts, portfolios or personal data are sent.",
    reviewer: "AI reviewer",
    default: " (default)",
    newsDays: "News of the last … days",
    button: "Start review",
    again: "Run review again",
    usage: "{{used}} of {{limit}} reviews with {{name}} used this month",
    noReviewers: "There are no AI reviewers yet; ask the admin.",
    defaultIn: "The default AI reviewer is set in your <link>settings</link>.",
  },
  result: {
    running:
      "The review is running (started {{started}}). This takes a few minutes; you can leave the page meanwhile.",
    failed: "The review failed: {{error}}",
    confirmed: "confirmed",
    notConfirmed: "not confirmed yet",
    modified: "modified",
    outdated: "outdated: the draft changed since",
    scoring: "scoring v{{version}}",
    news: "news {{from}} – {{to}}",
    whyChanged: "Why the result was changed:",
    notAdvice:
      "AI reviews can be wrong or incomplete, and are not financial advice. You decide what to change.",
    change: "Change result",
  },
  score: {
    totalLabel: "Total score",
    ai: "AI",
    yours: "Yours",
    total: "Total, {{who}}",
    outOf: "{{score}} / 10",
    aspectAi: "{{name}}, AI",
    aspectYours: "{{name}}, yours",
    yoursShort: "yours",
    aiValue: "(AI {{score}})",
  },
  aspects: {
    T1: "Core claim",
    T2: "Value drivers",
    T3: "Risks",
    T4: "Break conditions and warning signals",
    T5: "Fit and alternatives",
    T6: "Current evidence",
    P1: "Coverage",
    P2: "Weighting",
    P3: "Bands",
    P4: "Exits",
    P5: "Concentration",
    P6: "Rationales",
  },
  sources: "Sources",
  suggestions: {
    title: "Suggestions",
    note: "Nothing is changed automatically; take over what you agree with into the draft.",
    thesis_text: "Thesis text",
    thesis_status: "Thesis status",
    policy_position: "Position",
  },
  modify: {
    form: "Change result",
    intro:
      "Your values are shown next to the AI's, which stay visible. Choose “AI” to keep the AI's value.",
    keepAi: "AI ({{value}})",
    verdict: "Verdict",
    note: "Why do you change the result?",
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
  details: {
    changedBecause: "Changed because: {{note}}",
  },
  course: {
    label: "Review score over the revisions",
    caption: "Total review score per revision",
    point: "{{label}}: {{score}} of 10",
    tooltip: ": {{score}} / 10",
    tick: "r{{no}}",
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
    form: "Prüfung starten",
    introThesis:
      "Eine KI beurteilt die Anlagethese nach sechs Aspekten und prüft sie an aktuellen Nachrichten. Das Ergebnis wird bestätigt, wenn du den Entwurf aktivierst; vorher kannst du es ändern.",
    introPolicy:
      "Eine KI beurteilt nach sechs Aspekten, wie gut die Zielstruktur zur Anlagethese passt. Das Ergebnis wird bestätigt, wenn du den Entwurf aktivierst; vorher kannst du es ändern.",
    dataThesis:
      "Dafür wird der Text der Anlagethese an den Anbieter deines KI-Reviewers gesendet, der im Web nach Nachrichten sucht. ",
    dataPolicy:
      "Dafür werden der Text der Anlagethese und die Zielstruktur (Anteile, Schwellen, Exit-Markierungen, Begründungen) an den Anbieter deines KI-Reviewers gesendet. ",
    dataNothingElse: "Es werden keine Beträge, Portfolios oder persönlichen Daten gesendet.",
    reviewer: "KI-Reviewer",
    default: " (Standard)",
    newsDays: "Nachrichten der letzten … Tage",
    button: "Prüfung starten",
    again: "Prüfung erneut ausführen",
    usage: "{{used}} von {{limit}} Prüfungen mit {{name}} in diesem Monat verwendet",
    noReviewers: "Es gibt noch keine KI-Reviewer; frag den Admin.",
    defaultIn: "Den Standard-KI-Reviewer legst du in deinen <link>Einstellungen</link> fest.",
  },
  result: {
    running:
      "Die Prüfung läuft (gestartet {{started}}). Das dauert einige Minuten; du kannst die Seite inzwischen verlassen.",
    failed: "Die Prüfung ist fehlgeschlagen: {{error}}",
    confirmed: "bestätigt",
    notConfirmed: "noch nicht bestätigt",
    modified: "geändert",
    outdated: "veraltet: der Entwurf wurde seither geändert",
    scoring: "Bewertung v{{version}}",
    news: "Nachrichten {{from}} – {{to}}",
    whyChanged: "Warum das Ergebnis geändert wurde:",
    notAdvice:
      "KI-Prüfungen können falsch oder unvollständig sein und sind keine Finanzberatung. Du entscheidest, was du änderst.",
    change: "Ergebnis ändern",
  },
  score: {
    totalLabel: "Gesamtbewertung",
    ai: "KI",
    yours: "Deine",
    total: "Gesamt, {{who}}",
    outOf: "{{score}} / 10",
    aspectAi: "{{name}}, KI",
    aspectYours: "{{name}}, deine",
    yoursShort: "deine",
    aiValue: "(KI {{score}})",
  },
  aspects: {
    T1: "Kernaussage",
    T2: "Werttreiber",
    T3: "Risiken",
    T4: "Bruchbedingungen und Warnsignale",
    T5: "Eignung und Alternativen",
    T6: "Aktuelle Belege",
    P1: "Abdeckung",
    P2: "Gewichtung",
    P3: "Bänder",
    P4: "Exits",
    P5: "Konzentration",
    P6: "Begründungen",
  },
  sources: "Quellen",
  suggestions: {
    title: "Vorschläge",
    note: "Nichts wird automatisch geändert; übernimm in den Entwurf, was du für richtig hältst.",
    thesis_text: "Text der Anlagethese",
    thesis_status: "Status der Anlagethese",
    policy_position: "Position",
  },
  modify: {
    form: "Ergebnis ändern",
    intro:
      "Deine Werte stehen neben denen der KI, die sichtbar bleiben. Wähle «KI», um den Wert der KI zu behalten.",
    keepAi: "KI ({{value}})",
    verdict: "Urteil",
    note: "Warum änderst du das Ergebnis?",
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
  details: {
    changedBecause: "Geändert, weil: {{note}}",
  },
  course: {
    label: "Bewertung der Prüfungen über die Revisionen",
    caption: "Gesamtbewertung der Prüfung pro Revision",
    point: "{{label}}: {{score}} von 10",
    tooltip: ": {{score}} / 10",
    tick: "r{{no}}",
  },
};
