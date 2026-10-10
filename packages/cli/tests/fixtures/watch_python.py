"""Real provider SDK calls to the local acceptance mock, never a paid service."""

import asyncio
import os

import anthropic
import openai
from agentscope_sdk import AgentScope

origin = os.environ["WATCH_MOCK_ORIGIN"]
options = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "private-prompt-sentinel"}],
}
client = openai.OpenAI(
    api_key="mock-provider-key", base_url=origin + "/v1", max_retries=0
)
claude = anthropic.Anthropic(
    api_key="mock-provider-key", base_url=origin, max_retries=0
)
claude_options = {
    "model": "claude-test",
    "max_tokens": 10,
    "messages": options["messages"],
}

if os.environ.get("WATCH_FIXTURE_MODE") == "grounding":
    with (
        AgentScope.from_watch() as scope,
        scope.span("checked answer", "agent"),
        scope.llm("answer", "gpt-4o-mini") as usage,
    ):
        answer = client.chat.completions.create(**options)
        usage["input_tokens"] = answer.usage.prompt_tokens
        usage["output_tokens"] = answer.usage.completion_tokens
        scope.record_grounding(usage, 2, "local-reference-check")
else:
    assert (
        client.chat.completions.create(**options).choices[0].message.content
        == "private-answer-sentinel"
    )
    assert (
        client.responses.create(
            model="gpt-4o-mini", input="private-prompt-sentinel"
        ).usage.input_tokens
        == 13
    )
    with client.chat.completions.create(
        **options, stream=True, stream_options={"include_usage": True}
    ) as stream:
        assert list(stream)[-1].usage.completion_tokens == 7
    assert (
        list(
            client.responses.create(
                model="gpt-4o-mini", input="private-prompt-sentinel", stream=True
            )
        )[-1].type
        == "response.completed"
    )
    assert claude.messages.create(**claude_options).usage.input_tokens == 5
    with claude.messages.create(**claude_options, stream=True) as stream:
        assert list(stream)[-1].type == "message_stop"
    try:
        client.chat.completions.create(**{**options, "model": "fail"})
    except openai.InternalServerError:
        pass
    else:
        raise AssertionError("Provider errors must be preserved")

    async def asynchronous():
        async with openai.AsyncOpenAI(
            api_key="mock-provider-key", base_url=origin + "/v1", max_retries=0
        ) as api:
            assert (
                await api.chat.completions.create(**options)
            ).usage.prompt_tokens == 11
            assert (
                await api.responses.create(
                    model="gpt-4o-mini", input="private-prompt-sentinel"
                )
            ).usage.output_tokens == 5
            async with await api.chat.completions.create(
                **options, stream=True, stream_options={"include_usage": True}
            ) as stream:
                chunks = [chunk async for chunk in stream]
                assert chunks[-1].usage.completion_tokens == 7
            stream = await api.responses.create(
                model="gpt-4o-mini", input="private-prompt-sentinel", stream=True
            )
            assert [chunk async for chunk in stream][-1].type == "response.completed"
        async with anthropic.AsyncAnthropic(
            api_key="mock-provider-key", base_url=origin, max_retries=0
        ) as api:
            assert (
                await api.messages.create(**claude_options)
            ).usage.output_tokens == 3
            async with await api.messages.create(
                **claude_options, stream=True
            ) as stream:
                assert [chunk async for chunk in stream][-1].type == "message_stop"

    asyncio.run(asynchronous())
    with AgentScope.from_watch() as scope:

        @scope.trace_tool
        def lookup():
            return "private-tool-result-sentinel"

        @scope.trace_agent
        def grouped_agent():
            for _ in range(5):
                lookup()
            client.chat.completions.create(**options)

        grouped_agent()
