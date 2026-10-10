"""Metadata-only, nonblocking SDK. Export failures never interrupt an agent."""

import contextvars
import functools
import hashlib
import inspect
import json
import math
import queue
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

_context = contextvars.ContextVar("agentscope_trace", default=None)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class AgentScope:
    @classmethod
    def from_watch(cls):
        """Use the project-scoped connection established by watch/run."""
        import os
        from pathlib import Path

        try:
            endpoint = os.environ["AGENTSCOPE_WATCH_URL"]
            key = Path(os.environ["AGENTSCOPE_WATCH_KEY_FILE"]).read_text().strip()
            name = os.environ["AGENTSCOPE_WATCH_AGENT_NAME"]
        except (KeyError, OSError):
            raise ValueError(
                "Launch this application with agentscope watch or agentscope run first"
            ) from None
        return cls(
            endpoint,
            key,
            name,
            framework="Automatic LLM instrumentation",
            agent_id=os.environ.get("AGENTSCOPE_WATCH_AGENT_ID"),
        )

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
        agent_id=None,
    ):
        if (
            not isinstance(queue_size, int)
            or isinstance(queue_size, bool)
            or queue_size < 1
        ):
            raise ValueError("queue_size must be a positive integer")
        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or not 1 <= batch_size <= 1000
        ):
            raise ValueError("batch_size must be between 1 and 1000")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self.endpoint, self.api_key, self.agent_name = (
            endpoint.rstrip("/"),
            api_key,
            agent_name,
        )
        self.environment, self.framework = environment, framework
        # Watch already provisioned this project-scoped agent; reuse its ID.
        self._agent_id = agent_id
        self.timeout, self.batch_size = timeout, batch_size
        self._queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._abort = threading.Event()
        self._lock = threading.Lock()
        self._deadline = None
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
        remaining = (
            self.timeout
            if self._deadline is None
            else min(self.timeout, self._deadline - time.monotonic())
        )
        if remaining <= 0 or self._abort.is_set():
            raise OSError("Exporter shutdown deadline reached")
        with urllib.request.urlopen(request, timeout=remaining) as response:
            return json.load(response)

    def _enqueue(self, event):
        with self._lock:
            if self._stop.is_set():
                self.stats["dropped_events"] += 1
                return
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self.stats["dropped_events"] += 1

    def _discard(self):
        with self._lock:
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                    self.stats["dropped_events"] += 1
                except queue.Empty:
                    break

    def _export(self):
        agent_id = self._agent_id
        while not self._stop.is_set() or not self._queue.empty():
            if self._abort.is_set() or (
                self._deadline is not None and time.monotonic() >= self._deadline
            ):
                self._discard()
                return
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
                if self._abort.is_set() or (
                    self._deadline is not None and time.monotonic() >= self._deadline
                ):
                    with self._lock:
                        self.stats["dropped_events"] += len(batch)
                    break
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
                        with self._lock:
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
        state = {
            "trace_id": trace_id,
            "run_id": run_id,
            "span_id": span_id,
            "scope": self,
            "kind": "agent" if root else kind,
        }
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

    @staticmethod
    def record_grounding(usage, unsupported_claims, evaluator):
        """Attach an application's reference-based evaluation to an LLM span.

        This records an external assessment; it does not infer factual accuracy.
        Pass the usage dictionary yielded by scope.llm or scope.span.
        """
        if (
            type(unsupported_claims) is not int
            or not 0 <= unsupported_claims <= 1_000_000
        ):
            raise ValueError(
                "unsupported_claims must be an integer between 0 and 1000000"
            )
        if not isinstance(evaluator, str) or not 1 <= len(evaluator) <= 100:
            raise ValueError(
                "evaluator must be a nonempty label of at most 100 characters"
            )
        usage["attributes"]["grounding"] = {
            "unsupported_claims": unsupported_claims,
            "evaluator": evaluator,
        }

    def close(self, timeout=10):
        """Drain until the deadline; return whether the exporter has terminated.

        An already active request retains the configured socket timeout.
        After a close deadline no new request starts and queued events are counted
        as dropped. Call close again to wait for an in-flight request if needed.
        """
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("close timeout must be nonnegative and finite")
        with self._lock:
            if self._deadline is None:
                self._deadline = time.monotonic() + timeout
            self._stop.set()
        self._thread.join(timeout)
        if self._thread.is_alive():
            self._abort.set()
            self._discard()
            return False
        return True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
