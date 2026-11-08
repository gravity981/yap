"""Messages of the reviews, rebalances and LLM adapters."""

MESSAGES: dict[str, str] = {
    # LLM providers (llm/*); `detail` is the provider's own text and stays as it is
    "provider_status": "{provider} answered with error {status}",
    "provider_status_detail": "{provider} answered with error {status}: {detail}",
    "provider_rejected_key": "{provider} rejected the API key",
    "provider_no_model": "{provider} has no model {model}",
    "provider_timeout": "{provider} did not answer in time",
    "provider_unreachable": "{provider} could not be reached",
    "provider_declined": "{provider} declined the request",
    "provider_no_answer": "{provider} returned no answer",
    "provider_search_unfinished": "{provider} did not finish the web search",
    "provider_stopped": "{provider} stopped the answer ({reason})",
    "answer_too_long": "The answer was too long and was cut off",
    # A provider's text as it is, e.g. from the fake provider of the tests
    "provider_error": "{detail}",
    # Answers of the reviews (services/review_prompts.py)
    "answer_no_json": "The answer contains no JSON object",
    "answer_json_invalid": "The answer is no valid JSON: {error}",
    "answer_field_invalid": "{field}: {error}",
    "answer_prompt_id_unknown": "The answer has no valid prompt ID; copy the prompt again",
    "answer_prompt_id_other_draft": "The answer belongs to the prompt of another draft",
    "answer_aspects_wrong": "The answer must score exactly the aspects {aspects}",
    "answer_prompt_id_wrong": "The answer must repeat the prompt ID {prompt_id}",
    "score_invalid": "Score {score} is not between 0 and 10 in steps of 0.5",
    # Reviews (services/reviews.py, api/routers/reviews.py)
    "review_reviewer_not_found": "AI reviewer {id} not found",
    "review_choose_reviewer": "Choose an AI reviewer",
    "review_reviewer_archived": "The AI reviewer {name} is no longer available; choose another one",
    "review_reviewer_disabled": (
        "The AI reviewer {name} is disabled; choose another one or ask the admin"
    ),
    "review_reviewer_unusable": "The AI reviewer {name} cannot be used: {detail} Ask the admin.",
    "review_reviewer_no_reviews": "The AI reviewer {name} includes no reviews",
    "review_limit_reached": "All {limit} reviews with {name} of this month are used",
    "review_policy_no_draft": "Policy {name} has no draft",
    "review_policy_not_active": "Policy {name} has no active version to review",
    "review_running": "A review of this draft is still running",
    "review_running_wait": "A review of this draft is still running; wait for it to finish",
    "review_no_reviewer": "The review has no AI reviewer",
    "review_not_found": "Review {id} not found",
    "review_news_days_invalid": "The news period must be between 1 and {max} days",
    "review_interrupted": "Interrupted by a restart of the app; start the review again",
    "review_failed_unexpectedly": "The review failed unexpectedly ({detail})",
    "review_version_not_found": "Version {version_no} of policy {policy} not found",
    "review_version_no_review": "{version} has no review",
    # Suggestions and proposals (services/suggestions.py, REV-07, REV-22)
    "suggestion_not_found": "Suggestion {id} not found",
    "suggestion_review_confirmed": "The review is confirmed; its suggestions cannot change",
    "suggestion_without_change": "This suggestion is from an older review and cannot be taken over",
    "suggestion_not_open": "This suggestion was already taken over or dismissed",
    "suggestion_is_open": "This suggestion is neither taken over nor dismissed",
    "suggestion_position_missing": "The draft has no position {ticker} any more",
    "suggestion_position_exists": "The draft already has a position {ticker}",
    "suggestion_no_draft": "The draft this suggestion was taken over into no longer exists",
    # Rebalances (services/rebalances.py)
    "rebalance_values_missing": "Enter the portfolio's current values first",
    "rebalance_snapshot_not_found": "Snapshot {id} not found",
    "rebalance_policy_changed": (
        "The policy changed since the preview; calculate the rebalance again"
    ),
    "rebalance_no_instruction": "No {phase} instruction for {ticker}",
    "rebalance_executed_negative": "Executed amounts must be 0 or more",
    "rebalance_buffer_exceeded": "Buffer buys together exceed the cash buffer",
    "rebalance_sell_exceeds": "Sell of {ticker} exceeds the position's value",
    "rebalance_not_found": "Rebalance {id} not found",
    "rebalance_cycles_invalid": "Cycles must be between 1 and {max}",
}
