"""Recorded-style LLM answers for review tests (test strategy §6). Without a prompt ID,
the fake LLM fills in the one of its request (tests/fixtures.py)."""

import json
from typing import Any

THESIS_SCORES = (7, 6, 8, 5, 7, 6.5)  # thesis score 6.5 (39.5 / 6 = 6.58 -> 6.5)
POLICY_SCORES = (8, 7, 6, 9, 7.5, 8)  # target-structure score 7.5 (45.5 / 6 = 7.58 -> 7.5)
# The review's score: (6.5 + 7.5) / 2 = 7


PROMPT_ID = "R1-20260115T100000Z-90-000000"


def answer(
    verdict: str = "warning",
    scores: tuple[float, ...] = THESIS_SCORES,
    structure: tuple[float, ...] | None = POLICY_SCORES,
    prompt_id: str | None = None,
    **extra: Any,
) -> str:
    """A review of the whole policy; `structure=None` for a draft without positions."""
    aspects = [
        {"code": f"T{i}", "score": score, "reasoning": f"T{i} reasoning [1]"}
        for i, score in enumerate(scores, 1)
    ]
    aspects += [
        {"code": f"P{i}", "score": score, "reasoning": f"P{i} reasoning"}
        for i, score in enumerate(structure or (), 1)
    ]
    return json.dumps(
        {
            **({"prompt_id": prompt_id} if prompt_id else {}),
            "aspects": aspects,
            "verdict": verdict,
            "verdict_reason": "Warning signals are observed [1].",
            "sources": [
                {
                    "title": "ETF inflows rise",
                    "published_on": "2026-01-10",
                    "url": "https://news.example/etf",
                },
                {"title": "Undated", "published_on": "soon", "url": "https://news.example/x"},
            ],
            "suggestions": [{"kind": "thesis_text", "content": "Add a time horizon."}],
            **extra,
        }
    )


def thesis_answer(**kwargs: Any) -> str:
    """An answer for a draft without positions: T1-T6 only."""
    return answer(structure=None, **kwargs)
