"""Metadata-only OpenAI and Anthropic hooks; provider dependencies stay in the app."""

# Monitoring errors must not alter application behavior; logging provider
# exceptions could disclose user content or credentials.
# ruff: noqa: BLE001, S110

import atexit
import functools
import importlib
import importlib.abc
import importlib.machinery
import os
import sys
import threading
from urllib.parse import urlsplit
from uuid import uuid4

_scope = None
_lock = threading.Lock()
_active = set()


def field(value, name, default=None):
    return (
        value.get(name, default)
        if isinstance(value, dict)
        else getattr(value, name, default)
    )


def scope():
    global _scope
    with _lock:
        if _scope is None:
            from agentscope_sdk import AgentScope

            _scope = AgentScope.from_watch()
        return _scope


class Call:
    def __init__(self, provider, operation, options):
        from agentscope_sdk import _context, timestamp

        self.finished = False
        parent = _context.get()
        self.sink = parent["scope"] if parent else scope()
        self.usage = {}
        self.model = (
            options.get("model") if isinstance(options.get("model"), str) else None
        )
        self.model = self.model[:100] if self.model else None
        self.provider = provider
        self.operation = operation
        self.root = {
            "agent_id": "",
            "run_id": str(uuid4()),
            "trace_id": uuid4().hex,
            "span_id": uuid4().hex[:16],
            "parent_span_id": None,
            "kind": "agent",
            "name": f"{provider}.{operation}",
            "run_name": f"{provider}.{operation}",
            "started_at": timestamp(),
        }
        self.llm = {
            **self.root,
            "kind": "llm",
            "span_id": uuid4().hex[:16],
            "parent_span_id": self.root["span_id"],
        }
        if parent:
            self.llm.update(
                run_id=parent["run_id"],
                trace_id=parent["trace_id"],
                parent_span_id=parent["span_id"],
            )
            self.root = None
        with _lock:
            _active.add(self)
        if self.root:
            self.emit(self.root, "running")
        self.emit(self.llm, "running")

    def emit(self, event, status, ended=None, error=None):
        is_llm = event["kind"] == "llm"
        observed = "input_tokens" in self.usage and "output_tokens" in self.usage
        self.sink._enqueue(
            {
                **event,
                "event_id": str(uuid4()),
                "status": status,
                "ended_at": ended,
                "error": error,
                "model": self.model if is_llm else None,
                "input_tokens": self.usage.get("input_tokens", 0) if is_llm else 0,
                "output_tokens": self.usage.get("output_tokens", 0) if is_llm else 0,
                "attributes": {
                    "provider": self.provider,
                    "capture": "automatic",
                    "usage_observed": observed,
                }
                if is_llm
                else {"capture": "automatic"},
            }
        )

    def observe(self, result):
        # Parse usage metadata only. Prompt, messages, generated text and tool
        # arguments are never placed in telemetry.
        if field(result, "type") in ("error", "response.failed") or field(
            result, "error"
        ):
            self.finish("failed", "ProviderError")
        message = field(result, "message") or field(result, "response") or result
        model = field(message, "model")
        if isinstance(model, str):
            self.model = model[:100]
        usage = field(message, "usage") or field(result, "usage")
        if usage:
            for target, names in (
                ("input_tokens", ("input_tokens", "prompt_tokens")),
                ("output_tokens", ("output_tokens", "completion_tokens")),
            ):
                for name in names:
                    value = field(usage, name)
                    if type(value) is int and 0 <= value <= 1_000_000_000:
                        self.usage[target] = value
                        break

    def finish(self, status="completed", error=None):
        from agentscope_sdk import timestamp

        with _lock:
            if self.finished:
                return
            self.finished = True
            _active.discard(self)
        ended = timestamp()
        self.emit(self.llm, status, ended, error)
        if self.root:
            self.emit(self.root, status, ended, error)


def safe_call(provider, operation, options):
    try:
        from agentscope_sdk import _context

        parent = _context.get()
        if parent and parent.get("kind") == "llm":
            return None
        return Call(provider, operation, options)
    except Exception:
        return None


def observe(call, result):
    if call:
        try:
            call.observe(result)
        except Exception:
            pass


def finish(call, status="completed", error=None):
    if call:
        try:
            call.finish(status, error)
        except Exception:
            pass


class Stream:
    def __init__(self, original, call):
        self.original, self.call = original, call

    def __getattr__(self, name):
        return getattr(self.original, name)

    def __next__(self):
        try:
            value = next(self.original)
        except StopIteration:
            finish(self.call)
            raise
        except BaseException as exc:
            finish(self.call, "failed", type(exc).__name__)
            raise
        observe(self.call, value)
        return value

    async def __anext__(self):
        try:
            value = await self.original.__anext__()
        except StopAsyncIteration:
            finish(self.call)
            raise
        except BaseException as exc:
            finish(self.call, "failed", type(exc).__name__)
            raise
        observe(self.call, value)
        return value

    def __iter__(self):
        try:
            for item in self.original:
                observe(self.call, item)
                yield item
        except BaseException as exc:
            finish(
                self.call,
                "cancelled" if isinstance(exc, GeneratorExit) else "failed",
                type(exc).__name__,
            )
            raise
        else:
            finish(self.call)
        finally:
            finish(self.call, "cancelled")

    def __aiter__(self):
        async def iterate():
            try:
                async for item in self.original:
                    observe(self.call, item)
                    yield item
            except BaseException as exc:
                finish(
                    self.call,
                    "cancelled"
                    if type(exc).__name__ in ("GeneratorExit", "CancelledError")
                    else "failed",
                    type(exc).__name__,
                )
                raise
            else:
                finish(self.call)
            finally:
                finish(self.call, "cancelled")

        return iterate()

    def __enter__(self):
        self.original.__enter__()
        return self

    def __exit__(self, kind, value, traceback):
        try:
            return self.original.__exit__(kind, value, traceback)
        finally:
            finish(
                self.call,
                "failed" if kind else "cancelled",
                kind.__name__ if kind else None,
            )

    async def __aenter__(self):
        await self.original.__aenter__()
        return self

    async def __aexit__(self, kind, value, traceback):
        try:
            return await self.original.__aexit__(kind, value, traceback)
        finally:
            finish(
                self.call,
                "failed" if kind else "cancelled",
                kind.__name__ if kind else None,
            )

    def close(self):
        try:
            return self.original.close()
        finally:
            finish(self.call, "cancelled")


def wrap(cls, provider, operation, asynchronous=False):
    original = cls.create
    if getattr(original, "_agentscope_wrapped", False):
        return
    if asynchronous:

        @functools.wraps(original)
        async def invoke(*args, **options):
            call = safe_call(provider, operation, options)
            try:
                result = await original(*args, **options)
            except BaseException as exc:
                finish(call, "failed", type(exc).__name__)
                raise
            if options.get("stream") and call:
                return Stream(result, call)
            observe(call, result)
            finish(call)
            return result
    else:

        @functools.wraps(original)
        def invoke(*args, **options):
            call = safe_call(provider, operation, options)
            try:
                result = original(*args, **options)
            except BaseException as exc:
                finish(call, "failed", type(exc).__name__)
                raise
            if options.get("stream") and call:
                return Stream(result, call)
            observe(call, result)
            finish(call)
            return result

    invoke._agentscope_wrapped = True
    cls.create = invoke


def instrument(provider):
    resources = (
        [
            ("openai.resources.chat.completions", "Completions", "chat.completions"),
            ("openai.resources.responses", "Responses", "responses"),
        ]
        if provider == "openai"
        else [("anthropic.resources.messages", "Messages", "messages")]
    )
    for module, name, operation in resources:
        try:
            resource = importlib.import_module(module)
            wrap(getattr(resource, name), provider, operation)
            wrap(getattr(resource, f"Async{name}"), provider, operation, True)
        except (ImportError, AttributeError):
            print(
                f"AgentScope: {provider}.{operation} integration unavailable in this SDK version.",
                file=sys.stderr,
            )


class Loader(importlib.abc.Loader):
    def __init__(self, original, provider):
        self.original, self.provider = original, provider

    def create_module(self, spec):
        return self.original.create_module(spec)

    def exec_module(self, module):
        self.original.exec_module(module)
        try:
            instrument(self.provider)
        except Exception:
            print(
                f"AgentScope: {self.provider} monitoring unavailable; application continues.",
                file=sys.stderr,
            )


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in ("openai", "anthropic"):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            spec.loader = Loader(spec.loader, fullname)
        return spec


def shutdown():
    for call in list(_active):
        finish(call, "cancelled")
    if _scope:
        _scope.close(timeout=5)
        if _scope.stats["dropped_events"]:
            print(
                f"AgentScope: {_scope.stats['dropped_events']} telemetry events were dropped; check local API availability.",
                file=sys.stderr,
            )


def bootstrap():
    endpoint = os.environ.get("AGENTSCOPE_WATCH_URL")
    if not endpoint:
        return
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
    ):
        return
    sys.meta_path.insert(0, Finder())
    for provider in ("openai", "anthropic"):
        if provider in sys.modules:
            instrument(provider)
    atexit.register(shutdown)
