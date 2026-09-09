import asyncio
import time

import pytest

from src import agent
from src.agent import REGISTRY, Context, ScopeError, call, layers, orchestrate, select, tool


def test_decorator_registers_metadata():
    @tool("adds numbers", scope="public", cost=0.01)
    def adder(a: int = 1, b: int = 2):
        return a + b

    assert REGISTRY["adder"].description == "adds numbers"
    assert REGISTRY["adder"].cost == 0.01


def test_builtin_tools_present():
    assert {"weather", "balance", "calendar", "summarise"} <= set(REGISTRY)


def test_catalog_hides_out_of_scope():
    from src.agent import catalog

    assert "balance" not in catalog(Context())
    assert "balance" in catalog(Context(scopes={"public", "account"}))


def test_select_drops_unknown_tools(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, **k: '["weather", "not_a_tool"]')
    assert select("x", Context()) == ["weather"]


def test_select_survives_garbage(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, **k: "I'm not sure!")
    assert select("x", Context()) == []


def test_scope_enforced():
    with pytest.raises(ScopeError):
        asyncio.run(call("balance", Context()))


def test_scope_allows_when_granted():
    out = asyncio.run(call("balance", Context(scopes={"public", "account"})))
    assert "INR" in out


def test_layers_respect_dependencies():
    got = layers(["summarise", "weather", "calendar"])
    assert "summarise" in got[-1]
    assert {"weather", "calendar"} <= set(got[0])


def test_denied_tool_becomes_structured_error(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, **k: '["balance"]')
    results = asyncio.run(orchestrate("balance please", Context()))
    assert "error" in results["balance"]


def test_independent_tools_run_concurrently(monkeypatch):
    @tool("slow a")
    async def slow_a():
        await asyncio.sleep(0.3)
        return "a"

    @tool("slow b")
    async def slow_b():
        await asyncio.sleep(0.3)
        return "b"

    monkeypatch.setattr(agent, "complete", lambda m, **k: '["slow_a", "slow_b"]')
    t0 = time.perf_counter()
    results = asyncio.run(orchestrate("both", Context()))
    elapsed = time.perf_counter() - t0
    assert results == {"slow_a": "a", "slow_b": "b"}
    assert elapsed < 0.5, f"ran sequentially: {elapsed:.2f}s"
