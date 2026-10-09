"""Metadata-only, nonblocking SDK. Export failures never interrupt an agent."""

import contextvars
import functools
import hashlib
import inspect
import json
import queue
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

_context = contextvars.ContextVar("agentscope_trace", default=None)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class AgentScope:
    def __init__(
        self,
        endpoint,
        api_key,
        agent_name,
        environment="development",
        framework="Custom",
        timeout=3,
        queue_size=1000,
        batch_size=50,
    ):
        self.endpoint, self.api_key, self.agent_name = (
            endpoint.rstrip("/"),
            api_key,
            agent_name,
        )
        self.environment, self.framework = environment, framework
        self.timeout, self.batch_size = timeout, batch_size
        self._queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self.stats = {"exported_events": 0, "dropped_events": 0, "export_failures": 0}
        self._thread = threading.Thread(
            target=self._export, daemon=True, name="agentscope-exporter"
        )
        self._thread.start()

    def _request(self, path, body):
        request = urllib.request.Request(
            self.endpoint + "/api/v1/" + path,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def _enqueue(self, event):
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.stats["dropped_events"] += 1

    def _export(self):
        agent_id = None
        while not self._stop.is_set() or not self._queue.empty():
            try:
                batch = [self._queue.get(timeout=0.2)]
            except queue.Empty:
                continue
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            for attempt in range(3):
                try:
                    if not agent_id:
                        agent_id = self._request(
                            "agents",
                            {
                                "name": self.agent_name,
                                "environment": self.environment,
                                "framework": self.framework,
                            },
                        )["id"]
                    for event in batch:
                        event["agent_id"] = agent_id
                    self._request("telemetry/events", {"events": batch})
                    self.stats["exported_events"] += len(batch)
                    break
                except (OSError, ValueError, KeyError):
                    self.stats["export_failures"] += 1
                    if attempt == 2:
                        self.stats["dropped_events"] += len(batch)
                    else:
                        self._stop.wait(0.2 * (2**attempt))
            for _ in batch:
                self._queue.task_done()

    @contextmanager
    def span(
        self,
        name,
        kind="tool",
        model=None,
        input_tokens=0,
        output_tokens=0,
        attributes=None,
    ):
        parent = _context.get()
        root = parent is None
        trace_id = parent["trace_id"] if parent else uuid4().hex
        run_id = parent["run_id"] if parent else str(uuid4())
        span_id = uuid4().hex[:16]
        state = {"trace_id": trace_id, "run_id": run_id, "span_id": span_id}
        token = _context.set(state)
        started = timestamp()
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
            "attributes": attributes or {},
        }
        event = {
            "agent_id": "",
            "run_id": run_id,
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent["span_id"] if parent else None,
            "name": name,
            "kind": "agent" if root else kind,
            "started_at": started,
            "run_name": name if root else "Agent execution",
        }
        if root:
            self._enqueue({**event, "event_id": str(uuid4()), "status": "running"})
        status, error = "completed", None
        try:
            yield usage
        except BaseException as exc:
            status = "failed"
            # Exception class only; exception text can contain credentials or user content.
            error = type(exc).__name__
            raise
        finally:
            self._enqueue(
                {
                    **event,
                    **usage,
                    "event_id": str(uuid4()),
                    "status": status,
                    "error": error,
                    "ended_at": timestamp(),
                }
            )
            _context.reset(token)

    def _decorator(self, function, kind):
        def fingerprint(args, kwargs):
            # Stable metadata hashes only. No raw argument or result leaves the application.
            try:
                return hashlib.sha256(
                    json.dumps(
                        [args, kwargs],
                        sort_keys=True,
                        default=lambda v: type(v).__name__,
                    ).encode()
                ).hexdigest()
            except (TypeError, ValueError, RecursionError):
                return "unavailable"

        if inspect.iscoroutinefunction(function):

            @functools.wraps(function)
            async def async_wrapper(*args, **kwargs):
                with self.span(
                    function.__name__,
                    kind,
                    attributes={"argument_fingerprint": fingerprint(args, kwargs)},
                ) as usage:
                    result = await function(*args, **kwargs)
                    usage["attributes"]["result_fingerprint"] = fingerprint(
                        (result,), {}
                    )
                    return result

            return async_wrapper

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            with self.span(
                function.__name__,
                kind,
                attributes={"argument_fingerprint": fingerprint(args, kwargs)},
            ) as usage:
                result = function(*args, **kwargs)
                usage["attributes"]["result_fingerprint"] = fingerprint((result,), {})
                return result

        return wrapper

    def trace_agent(self, function):
        return self._decorator(function, "agent")

    def trace_tool(self, function):
        return self._decorator(function, "tool")

    def llm(self, name, model, input_tokens=0, output_tokens=0):
        return self.span(name, "llm", model, input_tokens, output_tokens)

    def heartbeat(self, name="progress"):
        with self.span(name, "progress"):
            pass

    def close(self, timeout=10):
        self._stop.set()
        self._thread.join(timeout)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
