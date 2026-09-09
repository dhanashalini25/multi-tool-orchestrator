# 04 - Multi-Tool Orchestrator

> A tool registry with scopes, dependencies and real parallelism.

**What it demonstrates:** Coordinating many tools safely rather than chaining if/else

**Status:** working implementation with passing tests. Built as a learning project to understand the pattern, not as a production service.

---

## Run it right now

No API key needed - every project ships with `MODEL=fake`, a deterministic
offline responder, so you can see the whole flow work before spending anything.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python -m src.main
pytest -q
```

To use a real model, edit `.env`:

```
MODEL=gpt-4o-mini            # + OPENAI_API_KEY
MODEL=claude-3-5-haiku-latest  # + ANTHROPIC_API_KEY
MODEL=ollama/llama3.1        # free, runs locally
```

## How it works

Tools register themselves with a `@tool` decorator that records a description, a required scope, a cost and any dependencies. The catalog shown to the model is filtered by the caller's scopes, so a model can't ask for a tool it was never allowed to see.

`select()` asks the model which tools apply and then throws away anything not in the registry - the model's answer is a suggestion, never an instruction. `layers()` sorts the chosen tools into dependency layers; everything within a layer runs concurrently with `asyncio.gather`, and a dependency cycle degrades to sequential execution instead of hanging.

A tool called without its scope raises `ScopeError`, which surfaces as a structured error in the results rather than crashing the run.

## What "done" means here

- Tools self-register with description, scope, cost and dependencies
- The tool catalog is filtered by the caller's scopes before the model sees it
- Tool names from the model are validated against the registry
- Independent tools run concurrently; the test proves it with wall-clock timing
- Dependent tools run in dependency order, and a cycle degrades gracefully
- A permission denial returns a structured error, not a crash

Every one of those lines has a test behind it in `tests/` - `pytest -q` is the
proof, not the README.

## Layout

```
src/llm.py             provider-agnostic completion, plus offline fake mode
src/fake.py            the canned responses that make MODEL=fake work
src/logging_setup.py   structured JSON logging
src/agent.py           the pattern itself
src/main.py            CLI entrypoint
tests/                 10 tests, all passing
```

## Next steps

- Expose the registry over MCP so any MCP client can drive these tools
- Add per-tool timeouts so one slow tool can't stall a layer
- Use the `cost` field to refuse a plan that exceeds a budget

## Reference

https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant

---

Part of a 12-project agentic AI series - [github.com/dhanashalini25](https://github.com/dhanashalini25?tab=repositories)
