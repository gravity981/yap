"""Messages of the API and its access checks."""

MESSAGES: dict[str, str] = {
    "not_logged_in": "Not logged in",
    "password_change_required": "The password must be changed first",
    "admins_only": "Only admins can manage accounts",
    "investors_only": "Only active investors can access investment data",
    "invalid_input": "The input is invalid",
    # get_owned: one per owned table, named after it
    "policy_not_found": "Policy {id} not found",
    "portfolio_not_found": "Portfolio {id} not found",
}
