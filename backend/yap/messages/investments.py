"""Messages of the investment services: theses, policies, portfolios, snapshots, the asset
catalog, rebalancing inputs and the JSON import (IMP-06)."""

MESSAGES: dict[str, str] = {
    # Theses
    "title_required": "Title must not be empty",
    "thesis_status_unknown": "Unknown status {status}",
    "visibility_unknown": "Unknown visibility {visibility}",
    "thesis_has_no_draft": "Thesis {id} has no draft",
    "thesis_has_draft": "The thesis already has a draft",
    "thesis_first_revision_kept": (
        "The first revision cannot be deleted; it is the thesis' only one"
    ),
    "change_note_required": "A change note is required",
    "thesis_revision_not_found": "Thesis revision {id} not found",
    "thesis_revision_no_not_found": "Revision {number} of thesis {id} not found",
    # Policies
    "name_required": "Name must not be empty",
    "policy_name_taken": "A policy named {name} already exists",
    "thesis_not_activated": "The thesis has no activated revision yet; activate its draft first",
    "policy_has_no_draft": "Policy {name} has no draft",
    "policy_has_draft": "Policy {name} already has a draft",
    "ticker_duplicate": "Ticker {ticker} appears more than once",
    "target_range": "Target must be between 0 and 100",
    "buy_threshold_range": "Buy threshold must be between -100 and 0",
    "sell_threshold_min": "Sell threshold must be 0 or more",
    "one_cash_buffer": "At most one cash buffer position is allowed",
    "policy_first_version_kept": (
        "The first version cannot be deleted; it is the policy's only version"
    ),
    "target_sum": (
        "Target allocations sum to {sum} %, which differs from 100 % "
        "by {difference} percentage points"
    ),
    "multiple_cash_buffers": "The policy contains more than one cash buffer position",
    "change_note_required_v2": "A change note is required from v2 on",
    "policy_thesis_current": "The policy already uses the newest thesis revision",
    "policy_thesis_revision_not_found": "Thesis revision {id} not found for this policy",
    "policy_has_portfolios": "A policy with assigned portfolios cannot be archived",
    "policy_archived": "Policy {name} is archived",
    "policy_version_not_found": "Policy version {id} not found",
    "policy_version_no_not_found": "Version {number} of policy {name} not found",
    "policy_no_active_version": "Policy {name} has no active version",
    "policy_not_active_yet": "Policy {name} has no active version yet",
    # Portfolios and snapshots
    "portfolio_name_taken": "A portfolio named {name} already exists",
    "portfolio_already_follows": "Portfolio {portfolio} already follows policy {policy}",
    "contribution_min": "The contribution must be 0 or more",
    "value_min": "Value must be 0 or more",
    "units_min": "Units must be 0 or more",
    "price_min": "The price must be 0 or more",
    "units_required": "Enter the units of {ticker}",
    "price_required": "Enter the price or the value of {ticker}; it has no earlier price",
    "value_without_units": "A position with 0 units has the value 0",
    "portfolio_currency_locked": "The currency cannot change once the portfolio has snapshots",
    "position_units_or_value": "A position needs its units or its value",
    "snapshot_not_found": "Snapshot {id} not found",
    # Rebalancing inputs (RB-01)
    "withdrawal_min": "The withdrawal must be 0 or more",
    "withdrawal_too_large": (
        "The withdrawal cannot exceed the portfolio value plus the contribution ({maximum})"
    ),
    # Asset catalog
    "ticker_required": "Ticker must not be empty",
    "ticker_unknown_add": "Unknown ticker {ticker}: name and type are needed to add it",
    "asset_type_unknown": "Unknown asset type {type}",
    # Import (IMP-06, IMP-08, IMP-09)
    "schema_not_found": "No schema for {type}",
    "invalid_json": "Invalid JSON: {message} (line {line}, column {column})",
    "schema_version_unsupported": (
        "Schema version {version} is not supported; this app reads version {major}.x"
    ),
    "schema_error": "{detail}",
    "import_ticker_unknown": "Unknown ticker {ticker}: name and type are needed",
    "asset_type_mismatch": "{ticker} is already in the asset catalog as {catalog_type}, not {type}",
    "import_target_sum": "Target allocations sum to {sum} %, which differs from 100 %",
}
