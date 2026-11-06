import type { Messages } from "../messages";

// Pages: login, change password, accounts, AI reviewers (src/pages).
export const en = {
  login: {
    description: "Log in with your account.",
    username: "Username",
    password: "Password",
    submit: "Log in",
    pending: "Logging in …",
    tooMany: "Too many failed attempts. Please wait 15 minutes and try again.",
    invalid: "Invalid username or password.",
    failed: "Login failed. Please try again.",
  },
  password: {
    title: "Change password",
    temporary: "You logged in with a temporary password. Choose your own password to continue.",
    current: "Current password",
    new: "New password",
    repeat: "Repeat new password",
    tooShort: "The new password needs at least {{min}} characters.",
    mismatch: "The new passwords do not match.",
    changed: "Your password was changed.",
    submit: "Change password",
  },
  accounts: {
    title: "Accounts",
    newAccount: "New account",
    username: "Username",
    role: "Role",
    currency: "Currency",
    status: "Status",
    created: "Created",
    actions: "Actions",
    roleAdmin: "admin",
    roleInvestor: "investor",
    active: "active",
    deactivated: "deactivated",
    temporaryPassword: "temporary password",
    roles: "Roles",
    currencyButton: "Currency",
    deactivate: "Deactivate",
    reactivate: "Reactivate",
    resetPassword: "Reset password",
    delete: "Delete",
    create: {
      description:
        "The account logs in with the temporary password and must then choose an own password.",
      submit: "Create",
      temporaryPassword: "Temporary password",
      baseCurrency: "Base currency",
    },
    roleChoice: {
      legend: "Roles",
      investor: "Investor: own theses, policies and portfolios",
      admin: "Admin: manages accounts and AI reviewers, sees no investment data of others",
    },
    rolesDialog: {
      title: "Roles of {{name}}",
      description:
        "The investor role can only be removed while the account owns no theses, policies or portfolios. The last active admin keeps the admin role.",
    },
    resetDialog: {
      title: "Reset password of {{name}}",
      description:
        "All sessions of this account end. The account must change the temporary password at the next login.",
    },
    currencyDialog: {
      title: "Base currency of {{name}}",
      description:
        "Can only be changed as long as the investor has not entered any portfolio values.",
    },
    deleteDialog: {
      title: "Delete {{name}}?",
      description:
        "This cannot be undone. The account is anonymised and can no longer log in; its history stays in the database but is unreachable. Shared theses stay readable.",
      submit: "Delete account",
      confirm: 'Type "{{name}}" to confirm',
    },
  },
  aiReviewers: {
    title: "AI reviewers",
    description:
      "An AI reviewer is an LLM that reviews theses and policies. For each one, you set the provider, the model, the API key and how many reviews each investor may start with it per month. Investors choose one of the enabled reviewers for each review; they set their default in their settings.",
    new: "New AI reviewer",
    dataNote:
      "Reviews send thesis texts, asset names and tickers, and for policy reviews the target structure to the chosen provider; never amounts, portfolios or account names. The provider's terms apply to that data and to the costs of its API.",
    noSecret:
      "APP_SECRET_KEY is not set on the server, so API keys cannot be stored or used. Set it in the server environment and restart the app.",
    none: "No AI reviewers yet, so investors cannot run reviews.",
    form: "AI reviewer {{name}}",
    disabled: "disabled",
    changed: "changed {{date}}",
    name: "Name",
    descriptionLabel: "Description for investors (optional)",
    descriptionPlaceholder: "e.g. thorough, slower",
    provider: "Provider",
    model: "Model",
    modelPlaceholder: "Model name as listed by the provider",
    apiKey: "API key",
    keyStored: "Stored key ends in {{last4}}; enter a new one to replace it",
    keyNew: "The provider's API key",
    limit: "Reviews per investor and month",
    enabled: "Enabled: investors can choose it and run reviews with it",
    archive: "Archive",
    test: "Test connection",
    testing: "Testing …",
    create: "Create",
    archiveDialog: {
      title: "Archive {{name}}?",
      description:
        "It disappears from all lists and cannot run reviews any more. Past reviews keep its name, provider and model. Investors who chose it must choose another one.",
    },
  },
  priceProviders: {
    title: "Price providers",
    description:
      "Where the prices of snapshots come from. Investors look up their tickers at the enabled providers and choose a listing; the prices are updated regularly. Each provider can be added once.",
    add: "Add a price provider",
    dataNote:
      "Providers receive only tickers, listing symbols and currency codes; never amounts, units, portfolios or account names. The provider's terms apply to its data.",
    builtIn: "built in",
    builtInDescription:
      "Exchange rates (ECB reference rates) for converting prices into the currency of a portfolio. Needs no key and cannot be changed.",
    form: "Price provider {{name}}",
    unofficial:
      "An unofficial interface without published limits; it may stop working at any time.",
    apiKeyOptional: "API key (optional)",
    limit: "Calls per day",
    limitHint: "Empty: no limit. Lookups and price updates count together, per day in UTC.",
    calls: "{{calls}} calls today (UTC)",
    callsOf: "{{calls}} of {{limit}} calls today (UTC)",
    quotaExhausted: "limit reached today",
    listingsInUse_one: "{{count}} listing in use",
    listingsInUse_other: "{{count}} listings in use",
    runResult: "last update: {{updated}} updated, {{skipped}} skipped (limit), {{failed}} failed",
    schedule: {
      title: "Price update",
      description:
        "Fetches the latest price of every listing in use and the exchange rates, at this time of day and then at the interval. Beyond a provider's daily limit, the oldest prices are updated first next time. On the server, `update-prices` runs it by hand.",
      time: "Time of day",
      zone: "Time zone",
      interval: "Interval",
      every_one: "every hour",
      every_other: "every {{count}} hours",
      next: "Next run: {{date}}",
      last: "Last run: {{date}} ({{trigger}})",
      scheduled: "scheduled",
      cli: "by hand",
      running: "– still running",
      never: "No run yet.",
    },
    enabled: "Enabled: used for lookups and price updates",
    create: "Add",
    archiveDialog: {
      title: "Archive {{name}}?",
      description:
        "It is no longer used for lookups and price updates; positions priced by it become manual. It can be added again later.",
    },
  },
};

// German in Swiss spelling (ss, no ß), addressing the user with "du"; see src/i18n/README.md
export const de: Messages<typeof en> = {
  login: {
    description: "Melde dich mit deinem Konto an.",
    username: "Benutzername",
    password: "Passwort",
    submit: "Anmelden",
    pending: "Anmeldung läuft …",
    tooMany: "Zu viele fehlgeschlagene Versuche. Warte bitte 15 Minuten und versuche es erneut.",
    invalid: "Benutzername oder Passwort ist falsch.",
    failed: "Anmeldung fehlgeschlagen. Versuche es bitte erneut.",
  },
  password: {
    title: "Passwort ändern",
    temporary:
      "Du hast dich mit einem temporären Passwort angemeldet. Wähle ein eigenes Passwort, um weiterzumachen.",
    current: "Aktuelles Passwort",
    new: "Neues Passwort",
    repeat: "Neues Passwort wiederholen",
    tooShort: "Das neue Passwort braucht mindestens {{min}} Zeichen.",
    mismatch: "Die neuen Passwörter stimmen nicht überein.",
    changed: "Dein Passwort wurde geändert.",
    submit: "Passwort ändern",
  },
  accounts: {
    title: "Konten",
    newAccount: "Neues Konto",
    username: "Benutzername",
    role: "Rolle",
    currency: "Währung",
    status: "Status",
    created: "Erstellt",
    actions: "Aktionen",
    roleAdmin: "Admin",
    roleInvestor: "Investor",
    active: "aktiv",
    deactivated: "deaktiviert",
    temporaryPassword: "temporäres Passwort",
    roles: "Rollen",
    currencyButton: "Währung",
    deactivate: "Deaktivieren",
    reactivate: "Reaktivieren",
    resetPassword: "Passwort zurücksetzen",
    delete: "Löschen",
    create: {
      description:
        "Das Konto meldet sich mit dem temporären Passwort an und muss danach ein eigenes Passwort wählen.",
      submit: "Erstellen",
      temporaryPassword: "Temporäres Passwort",
      baseCurrency: "Basiswährung",
    },
    roleChoice: {
      legend: "Rollen",
      investor: "Investor: eigene Anlagethesen, Anlagestrategien und Portfolios",
      admin: "Admin: verwaltet Konten und KI-Reviewer, sieht keine Anlagedaten anderer",
    },
    rolesDialog: {
      title: "Rollen von {{name}}",
      description:
        "Die Investor-Rolle kann nur entfernt werden, solange das Konto keine Anlagethesen, Anlagestrategien oder Portfolios besitzt. Der letzte aktive Admin behält die Admin-Rolle.",
    },
    resetDialog: {
      title: "Passwort von {{name}} zurücksetzen",
      description:
        "Alle Sitzungen dieses Kontos werden beendet. Das Konto muss das temporäre Passwort bei der nächsten Anmeldung ändern.",
    },
    currencyDialog: {
      title: "Basiswährung von {{name}}",
      description:
        "Kann nur geändert werden, solange der Investor noch keine Portfolio-Werte erfasst hat.",
    },
    deleteDialog: {
      title: "{{name}} löschen?",
      description:
        "Das kann nicht rückgängig gemacht werden. Das Konto wird anonymisiert und kann sich nicht mehr anmelden; sein Verlauf bleibt in der Datenbank, ist aber nicht mehr erreichbar. Geteilte Anlagethesen bleiben lesbar.",
      submit: "Konto löschen",
      confirm: "Gib «{{name}}» ein, um zu bestätigen",
    },
  },
  aiReviewers: {
    title: "KI-Reviewer",
    description:
      "Ein KI-Reviewer ist ein LLM, das Anlagethesen und Anlagestrategien prüft. Für jeden legst du den Anbieter, das Modell, den API-Schlüssel und die Anzahl Prüfungen fest, die jeder Investor pro Monat damit starten darf. Investoren wählen für jede Prüfung einen der aktivierten KI-Reviewer; ihren Standard legen sie in den Einstellungen fest.",
    new: "Neuer KI-Reviewer",
    dataNote:
      "Prüfungen senden Texte von Anlagethesen, Namen und Ticker der Anlagen und bei Anlagestrategien die Zielstruktur an den gewählten Anbieter; nie Beträge, Portfolios oder Kontonamen. Für diese Daten und die Kosten seiner API gelten die Bedingungen des Anbieters.",
    noSecret:
      "APP_SECRET_KEY ist auf dem Server nicht gesetzt, daher können API-Schlüssel weder gespeichert noch verwendet werden. Setze ihn in der Server-Umgebung und starte die App neu.",
    none: "Noch keine KI-Reviewer, daher können Investoren keine Prüfungen durchführen.",
    form: "KI-Reviewer {{name}}",
    disabled: "deaktiviert",
    changed: "geändert {{date}}",
    name: "Name",
    descriptionLabel: "Beschreibung für Investoren (optional)",
    descriptionPlaceholder: "z. B. gründlich, langsamer",
    provider: "Anbieter",
    model: "Modell",
    modelPlaceholder: "Modellname, wie ihn der Anbieter angibt",
    apiKey: "API-Schlüssel",
    keyStored:
      "Der gespeicherte Schlüssel endet auf {{last4}}; gib einen neuen ein, um ihn zu ersetzen",
    keyNew: "Der API-Schlüssel des Anbieters",
    limit: "Prüfungen pro Investor und Monat",
    enabled: "Aktiviert: Investoren können ihn wählen und damit Prüfungen durchführen",
    archive: "Archivieren",
    test: "Verbindung testen",
    testing: "Wird getestet …",
    create: "Erstellen",
    archiveDialog: {
      title: "{{name}} archivieren?",
      description:
        "Er verschwindet aus allen Listen und kann keine Prüfungen mehr durchführen. Frühere Prüfungen behalten seinen Namen, Anbieter und sein Modell. Investoren, die ihn gewählt haben, müssen einen anderen wählen.",
    },
  },
  priceProviders: {
    title: "Preisanbieter",
    description:
      "Woher die Preise der Stände kommen. Investoren suchen ihre Ticker bei den aktivierten Anbietern und wählen ein Listing; die Preise werden regelmässig aktualisiert. Jeder Anbieter kann einmal hinzugefügt werden.",
    add: "Preisanbieter hinzufügen",
    dataNote:
      "Anbieter erhalten nur Ticker, Listing-Symbole und Währungscodes; nie Beträge, Anzahlen, Portfolios oder Kontonamen. Für ihre Daten gelten die Bedingungen des Anbieters.",
    builtIn: "eingebaut",
    builtInDescription:
      "Wechselkurse (Referenzkurse der EZB), um Preise in die Währung eines Portfolios umzurechnen. Braucht keinen Schlüssel und kann nicht geändert werden.",
    form: "Preisanbieter {{name}}",
    unofficial:
      "Eine inoffizielle Schnittstelle ohne veröffentlichte Limits; sie kann jederzeit aufhören zu funktionieren.",
    apiKeyOptional: "API-Schlüssel (optional)",
    limit: "Abfragen pro Tag",
    limitHint:
      "Leer: kein Limit. Suchen und Preisaktualisierungen zählen zusammen, pro Tag in UTC.",
    calls: "{{calls}} Abfragen heute (UTC)",
    callsOf: "{{calls}} von {{limit}} Abfragen heute (UTC)",
    quotaExhausted: "Limit heute erreicht",
    listingsInUse_one: "{{count}} Listing in Verwendung",
    listingsInUse_other: "{{count}} Listings in Verwendung",
    runResult:
      "letzte Aktualisierung: {{updated}} aktualisiert, {{skipped}} übersprungen (Limit), {{failed}} fehlgeschlagen",
    schedule: {
      title: "Preisaktualisierung",
      description:
        "Holt den letzten Preis jedes verwendeten Listings und die Wechselkurse, zu dieser Uhrzeit und dann im Intervall. Über dem Tageslimit eines Anbieters werden beim nächsten Mal die ältesten Preise zuerst aktualisiert. Auf dem Server startet `update-prices` sie von Hand.",
      time: "Uhrzeit",
      zone: "Zeitzone",
      interval: "Intervall",
      every_one: "jede Stunde",
      every_other: "alle {{count}} Stunden",
      next: "Nächster Lauf: {{date}}",
      last: "Letzter Lauf: {{date}} ({{trigger}})",
      scheduled: "geplant",
      cli: "von Hand",
      running: "– läuft noch",
      never: "Noch kein Lauf.",
    },
    enabled: "Aktiviert: wird für Suchen und Preisaktualisierungen verwendet",
    create: "Hinzufügen",
    archiveDialog: {
      title: "{{name}} archivieren?",
      description:
        "Er wird nicht mehr für Suchen und Preisaktualisierungen verwendet; Positionen, deren Preis von ihm kommt, werden manuell. Er kann später wieder hinzugefügt werden.",
    },
  },
};
