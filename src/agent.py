"""Multi-Tool Orchestrator - a registry with scopes, dependencies and parallelism.

Tools register themselves with a decorator carrying their scope and cost. The
router asks the model which tools apply, refuses anything outside the caller's
scopes, then runs independent tools concurrently and dependent ones in order.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .llm import complete
from .logging_setup import log

DEMO = "Check the weather and the account balance, then summarise."


class ScopeError(PermissionError):
    """Raised when a tool is called without the scope it declares."""


@dataclass
class Tool:
    name: str
    fn: Callable[..., Any]
    description: str
    scope: str = "public"
    cost: float = 0.0
    depends_on: list[str] = field(default_factory=list)


REGISTRY: dict[str, Tool] = {}


def tool(description: str, *, scope: str = "public", cost: float = 0.0,
         depends_on: list[str] | None = None):
    """Register a function as a callable tool."""

    def deco(fn):
        REGISTRY[fn.__name__] = Tool(
            fn.__name__, fn, description, scope, cost, list(depends_on or [])
        )
        return fn

    return deco


@dataclass
class Context:
    scopes: set[str] = field(default_factory=lambda: {"public"})


# --------------------------------------------------------------- tools
@tool("Current weather for a city.")
async def weather(city: str = "Bengaluru") -> str:
    await asyncio.sleep(0.05)
    return f"{city}: 28C, clear"


@tool("Account balance in INR.", scope="account")
def balance(account: str = "primary") -> str:
    return f"{account}: 41250 INR"


@tool("Today's calendar.", scope="public")
def calendar(day: str = "today") -> str:
    return "10:00 standup, 15:00 interview prep"


@tool("Summarise everything gathered.", depends_on=["weather", "calendar"])
def summarise(**results) -> str:
    return "summary of: " + ", ".join(sorted(results)) if results else "nothing to summarise"


# ------------------------------------------------------------ routing
def catalog(ctx: Context) -> str:
    return "\n".join(
        f"- {t.name}: {t.description} (scope={t.scope})"
        for t in REGISTRY.values()
        if t.scope in ctx.scopes
    )


def select(task: str, ctx: Context) -> list[str]:
    """Ask the model which registered tools apply. Never trusts the answer blindly."""
    raw = complete([{
        "role": "user",
        "content": (
            f"Available tools:\n{catalog(ctx)}\n\nTask: {task}\n"
            "Reply with a JSON array of tool names, nothing else."
        ),
    }])
    match = re.search(r"\[.*?\]", raw, re.S)
    try:
        names = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        names = []
    chosen = [n for n in names if n in REGISTRY]
    log.info("tools_selected", extra={"asked": names, "kept": chosen})
    return chosen


def layers(names: list[str]) -> list[list[str]]:
    """Group tools into dependency layers; everything in a layer runs concurrently."""
    remaining = list(dict.fromkeys(names))
    done: set[str] = set()
    out: list[list[str]] = []

    while remaining:
        ready = [n for n in remaining if set(REGISTRY[n].depends_on) & set(remaining) == set()]
        if not ready:  # cycle - run the rest in declaration order rather than hang
            log.warning("dependency_cycle", extra={"remaining": remaining})
            ready = remaining[:]
        out.append(ready)
        done |= set(ready)
        remaining = [n for n in remaining if n not in done]
    return out


async def call(name: str, ctx: Context, **kwargs) -> Any:
    t = REGISTRY[name]
    if t.scope not in ctx.scopes:
        log.warning("permission_denied", extra={"tool": name, "scope": t.scope})
        raise ScopeError(f"{name} requires scope '{t.scope}'")
    if asyncio.iscoroutinefunction(t.fn):
        return await t.fn(**kwargs)
    return await asyncio.to_thread(t.fn, **kwargs)


async def orchestrate(task: str, ctx: Context | None = None) -> dict[str, Any]:
    ctx = ctx or Context()
    names = select(task, ctx)
    results: dict[str, Any] = {}

    for layer in layers(names):
        started = time.perf_counter()
        outcomes = await asyncio.gather(
            *(call(n, ctx, **({} if n != "summarise" else dict(results))) for n in layer),
            return_exceptions=True,
        )
        for name, outcome in zip(layer, outcomes):
            results[name] = (
                {"error": str(outcome)} if isinstance(outcome, Exception) else outcome
            )
        log.info("layer_done", extra={"tools": layer, "ms": int((time.perf_counter() - started) * 1000)})

    return results


def resolve_conflicts(results: dict[str, Any]) -> str:
    """When two tools disagree, pick one and record why."""
    values = [v for v in results.values() if isinstance(v, str)]
    if len(set(values)) <= 1:
        return values[0] if values else ""
    verdict = complete([{
        "role": "user",
        "content": "These tools disagree:\n"
                   + "\n".join(f"{k}: {v}" for k, v in results.items())
                   + "\nWhich is authoritative, and why? One sentence.",
    }])
    log.info("conflict_resolved", extra={"verdict": verdict[:200]})
    return verdict


def run(prompt: str) -> str:
    results = asyncio.run(orchestrate(prompt, Context(scopes={"public", "account"})))
    return json.dumps(results, indent=2, default=str)
