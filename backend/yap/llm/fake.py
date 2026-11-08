"""A stand-in provider for the end-to-end tests (test strategy §2, §6): it answers every
review with fixed scores and never calls the internet. Enabled with LLM_FAKE=1 and
refused in production (see api/app.py)."""

import json
import re
from typing import Any

from yap.llm.base import LlmConfig, LlmRequest

# Thesis 6.5 (39.5 / 6 = 6.58), target structure 7.5 (45.5 / 6 = 7.58), review 7 (7.0)
SCORES = (7, 6, 8, 5, 7, 6.5, 8, 7, 6, 9, 7.5, 8)

# Plausible but generic texts, so that screenshots of the app look real (docs/features.md)
REASONING = {
    "T1": "The belief is stated clearly, with a time horizon, and can be checked later.",
    "T2": "The investor fit matches the assets; each one has a role and a rationale.",
    "T3": "The main value drivers are named, but their expected size and timing stay vague.",
    "T4": "Key risks are listed with their likely impact; currency risk is covered as well.",
    "T5": "Break conditions exist, but two warning signals are not measurable as written.",
    "T6": "Recent news supports the thesis; no break condition is met at the moment.",
    "P1": "Every asset the thesis relies on has a position; nothing important is missing.",
    "P2": "Target weights follow the conviction the thesis describes for each asset.",
    "P3": "The bands are wide enough to avoid frequent trades without letting weights drift far.",
    "P4": "Exit flags agree with the break conditions; no exit is pending.",
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
        answer: dict[str, Any] = {
            "prompt_id": properties["prompt_id"]["enum"][0],
            "aspects": [
                {"code": code, "score": score, "reasoning": REASONING[code]}
                for code, score in zip(codes, SCORES, strict=False)
            ],
            **_verdict(request.prompt),
            "sources": [
                {
                    "title": "Example news: global equity funds see steady inflows",
                    "published_on": None,
                    "url": "https://example.com/news",
                }
            ],
            "suggestions": _suggestions(request.prompt if "P1" in codes else None),
            "proposals": [] if "P1" in codes else PROPOSALS,
        }
        return json.dumps(answer)


BROKEN_MARKER = "[fake-verdict: broken]"


def _verdict(prompt: str) -> dict[str, str]:
    """A thesis that contains the marker is reviewed as broken (RB-25 in the e2e tests)."""
    if BROKEN_MARKER in prompt:
        return {
            "verdict": "broken",
            "verdict_reason": "A break condition of the thesis is met [1].",
        }
    return {
        "verdict": "good",
        "verdict_reason": "Recent news supports the thesis; no break condition is met [1].",
    }


_EMPTY = {
    "section": None,
    "text": None,
    "ticker": None,
    "name": None,
    "type": None,
    "target_pct": None,
    "buy_threshold_pct": None,
    "sell_threshold_pct": None,
    "exit": None,
    "rationale": None,
}


def _suggestions(content: str | None) -> list[dict[str, Any]]:
    """A thesis section, and with positions a wider sell threshold of the first one."""
    result: list[dict[str, Any]] = [
        {
            **_EMPTY,
            "kind": "thesis_section",
            "reason": "Make the warning signals measurable, so a weakening is noticed in time.",
            "section": 7,
            "text": "- World GDP growth below 2 % for two years\n- Fund costs (TER) above 0.3 %",
        }
    ]
    match = re.search(r"^\| (?!Ticker\b)([^|\s]+) \|", content or "", re.MULTILINE)
    if match and not match.group(1).startswith("-"):
        result.append(
            {
                **_EMPTY,
                "kind": "position_change",
                "reason": "A wider band suits the volatility the thesis describes.",
                "ticker": match.group(1),
                "sell_threshold_pct": 30,
            }
        )
    return result


def _position(ticker: str, name: str, kind: str, target: int, band: int) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "type": kind,
        "target_pct": target,
        "buy_threshold_pct": -band,
        "sell_threshold_pct": band,
        "exit": False,
        "rationale": f"Expresses the thesis with {name}.",
    }


PROPOSALS = [
    {
        "name": "Focused",
        "description": "Close to the thesis, with higher risk.",
        "positions": [
            _position("VWRL", "Vanguard FTSE All-World", "ETF", 85, 20),
            _position("CASH", "Cash buffer", "cash_buffer", 15, 0),
        ],
    },
    {
        "name": "Broader",
        "description": "A world core with a smaller cash buffer.",
        "positions": [
            _position("VWRL", "Vanguard FTSE All-World", "ETF", 90, 20),
            _position("CASH", "Cash buffer", "cash_buffer", 10, 0),
        ],
    },
]
