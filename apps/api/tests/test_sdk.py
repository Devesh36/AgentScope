import asyncio

import pytest
from agentscope_sdk import AgentScope


@pytest.fixture
def scope(monkeypatch):
    monkeypatch.setattr(AgentScope, "_export", lambda self: None)
    return AgentScope(
        "http://unreachable.invalid", "not-a-real-key", "test-agent", queue_size=50
    )


def drain(scope):
    result = []
    while not scope._queue.empty():
        result.append(scope._queue.get_nowait())
    return result


def test_nested_async_contexts_remain_isolated_and_do_not_capture_content(scope):
    @scope.trace_tool
    async def tool(value):
        await asyncio.sleep(0)
        return "secret-output-" + value

    @scope.trace_agent
    async def run(value):
        return await tool(value)

    async def concurrent():
        return await asyncio.gather(run("private-a"), run("private-b"))

    assert asyncio.run(concurrent()) == [
        "secret-output-private-a",
        "secret-output-private-b",
    ]
    events = drain(scope)
    roots = [e for e in events if e["kind"] == "agent" and e["status"] == "completed"]
    assert len(roots) == 2 and len({e["trace_id"] for e in roots}) == 2
    for tool_event in [e for e in events if e["kind"] == "tool"]:
        root = next(e for e in roots if e["run_id"] == tool_event["run_id"])
        assert tool_event["parent_span_id"] == root["span_id"]
    assert "private-a" not in str(events) and "secret-output" not in str(events)


def test_exceptions_preserved_and_queue_bounded(scope):
    @scope.trace_agent
    def broken():
        raise ValueError("sensitive-token")

    with pytest.raises(ValueError, match="sensitive-token"):
        broken()
    events = drain(scope)
    assert events[-1]["status"] == "failed" and events[-1]["error"] == "ValueError"
    assert "sensitive-token" not in str(events)
    for _ in range(100):
        scope.heartbeat()
    assert scope._queue.qsize() == 50 and scope.stats["dropped_events"] > 0
