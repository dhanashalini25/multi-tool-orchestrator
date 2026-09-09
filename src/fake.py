"""Canned tool selection for MODEL=fake."""
from __future__ import annotations


def respond(messages: list[dict]) -> str:
    content = messages[-1]["content"]
    if "disagree" in content:
        return "The account tool is authoritative because it reads the ledger directly."
    names = ["weather", "calendar", "summarise"]
    if "account" in content:
        names.insert(1, "balance")
    return "[" + ", ".join(f'"{n}"' for n in names) + "]"
