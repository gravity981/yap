"""Messages of the price providers and exchange rates (PRC-01 to PRC-12)."""

MESSAGES: dict[str, str] = {
    # Provider requests
    "price_provider_unreachable": "{provider} cannot be reached ({detail})",
    "price_provider_auth": "{provider} refused the API key",
    "price_provider_quota": "The call limit of {provider} is reached for today",
    "price_provider_status": "{provider} answered with status {status}",
    "price_provider_unexpected": "{provider} sent an answer that cannot be read",
    "price_not_found": "{provider} has no price for {symbol}",
    "price_connection_ok": "Connected to {provider}",
    # Configuration (PRC-01)
    "price_provider_not_found": "Price provider {id} not found",
    "price_provider_unknown": "Unknown price provider {provider}",
    "price_provider_exists": "{provider} has been added already",
    "price_provider_built_in": "The built-in exchange rate source cannot be changed",
    # Lookup and price sources (PRC-02 to PRC-06)
    "price_no_provider": "No price provider is enabled; ask the admin",
    "price_source_kind_unknown": "Unknown price source {kind}",
    "price_listing_unavailable": "Listing {id} is not available",
    # Schedule of the price update (PRC-07)
    "time_of_day_invalid": "Enter the time of day as HH:MM",
    "interval_invalid": "The interval must be one of {intervals} hours",
}
