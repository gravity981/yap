"""Messages of the account and AI reviewer services."""

MESSAGES: dict[str, str] = {
    # Login and sessions (USR-01, USR-07, NFR-02)
    "login_locked": "Too many failed logins; try again after {until}",
    "login_invalid": "Invalid username or password",
    "session_expired": "Session expired",
    # Passwords (USR-03, USR-07)
    "password_too_short": "Passwords need at least {min} characters",
    "password_wrong": "The current password is wrong",
    "password_unchanged": "The new password must differ from the current one",
    # Language (USR-10)
    "language_unknown": "Unknown language {language}; choose one of {languages}",
    # Time zone (USR-11)
    "time_zone_unknown": "Unknown time zone {time_zone}",
    # Accounts (USR-02, USR-06, USR-09)
    "currency_invalid": "Currency must be a 3-letter ISO 4217 code",
    "username_empty": "Username must not be empty",
    "username_reserved": "Usernames must not start with 'deleted-'",
    "username_taken": "Username {username} is taken",
    "roles_required": "An account needs at least one role",
    "base_currency_required": "Investors need a base currency",
    "last_admin_keeps_role": "The last active admin keeps the admin role",
    "investor_role_in_use": (
        "The investor role cannot be removed while the account owns theses, policies or portfolios"
    ),
    "account_not_found": "Account {id} not found",
    "own_account_status": "Admins cannot change their own account status",
    "base_currency_investors_only": "Only investors have a base currency",
    # AI reviewers (REV-13 to REV-15)
    "ai_reviewer_not_found": "AI reviewer {id} not found",
    "ai_reviewer_name_required": "A name is required",
    "ai_reviewer_name_taken": "There is already an AI reviewer named {name}",
    "provider_unknown": "Unknown provider {provider}",
    "model_required": "A model is required",
    "limit_negative": "The limit must be 0 or more",
    "api_key_required": "An API key is required",
    "api_key_no_secret": "APP_SECRET_KEY is not set, so keys cannot be stored",
    "ai_reviewer_disabled": "The AI reviewer {name} is disabled",
    "connection_ok": "Connected to {provider}, model {model}",
    "test_failed_unexpectedly": "The test failed unexpectedly ({detail})",
    # Stored API keys (REV-15)
    "secret_missing": "APP_SECRET_KEY is not set on the server; API keys cannot be used",
    "secret_cannot_decrypt": (
        "The stored API key cannot be decrypted (APP_SECRET_KEY changed?); enter it again"
    ),
}
