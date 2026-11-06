"""A stand-in provider for the end-to-end tests (test strategy §2, §6): it answers every
review with fixed scores and never calls the internet. Enabled with LLM_FAKE=1 and
refused in production (see api/app.py)."""

import json
from typing import Any

from yap.llm.base import LlmConfig, LlmRequest

SCORES = (7, 6, 8, 5, 7, 6.5)  # total 6.5

# Plausible but generic texts, so that screenshots of the app look real (docs/features.md)
REASONING = {
    "T1": "The core claim is stated clearly and can be checked against later developments.",
    "T2": "The main value drivers are named, but their expected size and timing stay vague.",
    "T3": "Key risks are listed with their likely impact; currency risk is covered as well.",
    "T4": "Break conditions exist, but two warning signals are not measurable as written.",
    "T5": "The thesis explains why this asset was chosen over the obvious alternatives.",
    "T6": "Recent news supports the thesis; no break condition is met at the moment.",
    "P1": "Every asset the thesis relies on has a position; nothing important is missing.",
    "P2": "Target weights follow the conviction the thesis describes for each asset.",
    "P3": "The bands are wide enough to avoid frequent trades without letting weights drift far.",
    "P4": "Exit flags agree with the thesis status; no exit is pending.",
    "P5": "No single position dominates; the largest one is a broadly diversified fund.",
    "P6": "The rationales repeat the thesis well, one of them could be more specific.",
}


class FakeAdapter:
    def __init__(self, config: LlmConfig) -> None:
        self.config = config

    def check(self) -> None:
        return None

    def generate(self, request: LlmRequest) -> str:
        properties = request.json_schema["properties"]
        codes = properties["aspects"]["items"]["properties"]["code"]["enum"]
        thesis = "verdict" in properties
        answer: dict[str, Any] = {
            "aspects": [
                {"code": code, "score": score, "reasoning": REASONING[code]}
                for code, score in zip(codes, SCORES, strict=True)
            ],
            "suggestions": [
                {
                    "kind": "thesis_text" if thesis else "policy_position",
                    "content": "Make the warning signals measurable, e.g. with a threshold."
                    if thesis
                    else "Explain in the rationale why the bond share is not higher.",
                }
            ],
        }
        if thesis:
            answer["verdict"] = "intact"
            answer["sources"] = [
                {
                    "title": "Example news: global equity funds see steady inflows",
                    "published_on": None,
                    "url": "https://example.com/news",
                }
            ]
        return json.dumps(answer)
