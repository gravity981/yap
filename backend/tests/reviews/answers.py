"""Recorded-style LLM answers for review tests (test strategy §6). Without a prompt ID,
the fake LLM fills in the one of its request (tests/fixtures.py)."""

import json
from typing import Any

THESIS_SCORES = (7, 6, 8, 5, 7, 6.5)  # total 6.5 (39.5 / 6 = 6.58 -> 6.5)
POLICY_SCORES = (8, 7, 6, 9, 7.5, 8)  # total 7.5 (45.5 / 6 = 7.58 -> 7.5)


PROMPT_ID = "T1-20260115T100000Z-90-000000"


def thesis_answer(
    verdict: str = "needs_adaptation",
    scores: tuple[float, ...] = THESIS_SCORES,
    prompt_id: str | None = None,
    **extra: Any,
) -> str:
    return json.dumps(
        {
            **({"prompt_id": prompt_id} if prompt_id else {}),
            "aspects": [
                {"code": f"T{i}", "score": score, "reasoning": f"T{i} reasoning [1]"}
                for i, score in enumerate(scores, 1)
            ],
            "verdict": verdict,
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


def policy_answer(scores: tuple[float, ...] = POLICY_SCORES, prompt_id: str | None = None) -> str:
    return json.dumps(
        {
            **({"prompt_id": prompt_id} if prompt_id else {}),
            "aspects": [
                {"code": f"P{i}", "score": score, "reasoning": f"P{i} reasoning"}
                for i, score in enumerate(scores, 1)
            ],
            "suggestions": [],
        }
    )
