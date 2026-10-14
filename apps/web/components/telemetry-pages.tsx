"use client";
import { useState } from "react";
import Link from "next/link";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Clock3,
  Code2,
  Copy,
  Cpu,
  ExternalLink,
  Filter,
  GitBranch,
  Layers,
  Plus,
  Search,
  Terminal,
  TriangleAlert,
  Zap,
} from "lucide-react";
import type { Agent, Paginated, Run, Span } from "@/lib/types";
import { date, duration, money, number, spanDepth } from "@/lib/format";
import { useAction, useData, useWorkspace } from "./workspace";
import {
  Back,
  Badge,
  DataState,
  DemoNotice,
  Empty,
  Field,
  Json,
  PageHeader,
  Pagination,
  Panel,
} from "./common";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";
import { ExplorerActions, ExplorerSearch, useExplorerFilters } from "./explorer-filters";
export function AgentsPage() {
  const query = useData<Agent[]>("agents");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [framework, setFramework] = useState("Custom");
  const [environment, setEnvironment] = useState("development");
  const { act, pending } = useAction();
  const agents = (query.data || []).filter(
    (a) =>
      a.name.toLowerCase().includes(search.toLowerCase()) &&
      (status === "all" || a.status === status),
  );
  return (
    <>
      <PageHeader
        title="Agents"
        description="Every agent, its health, and the work behind it."
        actions={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus size={15} />
            Register agent
          </Button>
        }
      />
      <div className="filter-row">
        <div className="search-input">
          <Search size={15} />
          <input
            aria-label="Search agents"
            placeholder="Search agents…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          aria-label="Agent status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="all">All statuses</option>
          {["healthy", "active", "degraded", "idle"].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <span className="muted small">{agents.length} agents</span>
      </div>
      <DataState query={query}>
        {agents.length ? (
          <div className="agent-grid">
            {agents.map((a) => (
              <Link
                href={`/agents/${a.id}`}
                className="agent-card panel"
                key={a.id}
              >
                <div className="agent-card-heading">
                  <span className="agent-icon large">
                    <Bot size={22} />
                  </span>
                  <Badge value={a.status} />
                </div>
                <h2>{a.name.replace("demo/", "")}</h2>
                <div className="agent-tags">
                  <span>{a.framework}</span>
                  <span>{a.environment}</span>
                  {a.synthetic && <Badge value="demo" demo />}
                </div>
                <div className="agent-card-metrics">
                  <div>
                    <span>Success rate</span>
                    <strong>
                      {a.success_rate == null ? "—" : `${a.success_rate}%`}
                    </strong>
                  </div>
                  <div>
                    <span>Avg. latency</span>
                    <strong>{duration(a.average_latency_ms)}</strong>
                  </div>
                  <div>
                    <span>Tokens</span>
                    <strong>{number(a.tokens)}</strong>
                  </div>
                </div>
                <div className="agent-card-footer">
                  <span>
                    <Layers size={13} />
                    {number(a.run_count)} runs
                  </span>
                  <span>
                    {
                      a.recent_incidents.filter((i) => i.status !== "RESOLVED")
                        .length
                    }{" "}
                    recent incidents
                    <ChevronRight size={14} />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <Empty
            title={
              search || status !== "all"
                ? "No matching agents"
                : "Connect your first agent"
            }
            description="Register an agent, create a project API key in Settings, and send telemetry with the Python SDK."
            action={
              <Button variant="primary" onClick={() => setOpen(true)}>
                <Plus size={15} />
                Register agent
              </Button>
            }
          />
        )}
      </DataState>
      <Panel
        title="Instrument in minutes"
        subtitle="Your application owns the execution. AgentScope observes it."
      >
        <div className="sdk-callout">
          <div>
            <h3>A small integration. A complete execution story.</h3>
            <p>
              Track nested tools, model usage, and errors. Metadata is captured
              by default; prompts and responses stay with your application.
            </p>
            <Link className="text-link" href="/settings">
              Create an API key <ChevronRight size={14} />
            </Link>
          </div>
          <pre>
            <code>{`from agentscope_sdk import AgentScope\n\nscope = AgentScope(\n    endpoint="http://localhost:8000",\n    api_key="YOUR_PROJECT_API_KEY",\n    agent_name="my-agent",\n)\n\n@scope.trace_agent\nasync def run_agent(task):\n    return await agent.run(task)`}</code>
          </pre>
        </div>
      </Panel>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Register an agent"
        description="Create an identity for your agent. Telemetry will arrive through the project API key."
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const result = await act<Agent>(
              "agents",
              { name, framework, environment },
              "Agent registered",
            );
            if (result) {
              setOpen(false);
              setName("");
            }
          }}
        >
          <Field label="Agent name">
            <input
              required
              maxLength={120}
              placeholder="research-agent"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <div className="form-grid">
            <Field label="Framework">
              <select
                value={framework}
                onChange={(e) => setFramework(e.target.value)}
              >
                <option>Custom</option>
                <option>LangGraph</option>
                <option>OpenAI Agents</option>
                <option>CrewAI</option>
                <option>AutoGen</option>
              </select>
            </Field>
            <Field label="Environment">
              <select
                value={environment}
                onChange={(e) => setEnvironment(e.target.value)}
              >
                <option>development</option>
                <option>staging</option>
                <option>production</option>
              </select>
            </Field>
          </div>
          <div className="form-actions">
            <Button type="button" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={pending} type="submit">
              {pending ? "Registering…" : "Register agent"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
export function AgentDetail({ id }: { id: string }) {
  const query = useData<Agent>(`agents/${id}`);
  const a = query.data;
  return (
    <>
      <Back href="/agents">All agents</Back>
      <PageHeader
        title={a?.name.replace("demo/", "") || "Agent details"}
        description="Health, configuration, and recent execution history."
        actions={a && <Badge value={a.status} />}
      />
      <DataState query={query}>
        {a && (
          <>
            {a.synthetic && <DemoNotice />}
            <div className="detail-metrics">
              <Metric
                label="Success rate"
                value={a.success_rate == null ? "—" : `${a.success_rate}%`}
              />
              <Metric
                label="Average latency"
                value={duration(a.average_latency_ms)}
              />
              <Metric label="Token usage" value={number(a.tokens)} />
              <Metric label="Total runs" value={number(a.run_count)} />
            </div>
            <div className="two-col">
              <Panel title="Agent configuration">
                <div className="key-values">
                  <Row name="Framework" value={a.framework} />
                  <Row name="Environment" value={a.environment} />
                  <Row
                    name="Agent ID"
                    value={<span className="mono">{a.id}</span>}
                  />
                  <Row
                    name="Control capability"
                    value={
                      a.synthetic
                        ? "Isolated demo adapter"
                        : "Recommendation only"
                    }
                  />
                </div>
                <Json value={a.configuration} />
              </Panel>
              <Panel title="Recent incidents">
                {a.recent_incidents.length ? (
                  a.recent_incidents.map((i) => (
                    <Link
                      key={i.id}
                      className="incident-row"
                      href={`/incidents/${i.id}`}
                    >
                      <span className={`severity-bar severity-${i.severity}`} />
                      <div className="grow">
                        <strong>{i.title}</strong>
                        <span>{date(i.created_at)}</span>
                      </div>
                      <Badge value={i.status} />
                    </Link>
                  ))
                ) : (
                  <Empty
                    compact
                    title="No incidents"
                    description="No anomalous behavior has been detected for this agent."
                  />
                )}
              </Panel>
            </div>
            <Panel
              title="Recent runs"
              action={
                <Link className="text-link" href="/runs">
                  Run explorer <ChevronRight size={14} />
                </Link>
              }
            >
              {a.recent_runs.length ? (
                <RunTable runs={a.recent_runs} />
              ) : (
                <Empty
                  compact
                  title="Waiting for telemetry"
                  description="Send your first execution through the SDK or OTLP endpoint."
                />
              )}
            </Panel>
          </>
        )}
      </DataState>
    </>
  );
}
export function RunsPage() {
  const { hours, source } = useWorkspace();
  const { search, status, offset, searchKey, update, reset, setOffset } = useExplorerFilters("runs");
  const query = useData<Paginated<Run>>(
    `runs?hours=${hours}&limit=20&offset=${offset}&search=${encodeURIComponent(search)}${status !== "all" ? `&status=${status}` : ""}${source !== "all" ? `&synthetic=${source === "demo"}` : ""}`,
  );
  return (
    <>
      <PageHeader
        title="Run explorer"
        description="Follow every execution. Find exactly where things changed."
        filters
        actions={<ExplorerActions kind="runs" reset={reset} />}
      />
      <div className="filter-row">
        <ExplorerSearch key={searchKey} kind="runs" value={search} onChange={(value) => update({ q: value }, true)} />
        <select
          aria-label="Run status"
          value={status}
          onChange={(e) => update({ status: e.target.value })}
        >
          <option value="all">All statuses</option>
          {["running", "completed", "failed", "paused", "cancelled"].map(
            (s) => (
              <option key={s}>{s}</option>
            ),
          )}
        </select>
        <span className="muted small" role="status" aria-live="polite">
          {query.isPending ? "Loading executions…" : `${number(query.data?.total)} executions`}
        </span>
      </div>
      <DataState query={query}>
        <Panel
          title="Executions"
          subtitle="Persistent traces, real usage, and associated incidents"
        >
          {query.data?.items.length ? (
            <>
              <RunTable runs={query.data.items} />
              <Pagination
                offset={offset}
                total={query.data.total}
                onChange={setOffset}
              />
            </>
          ) : (
            <Empty
              title="No runs in this view"
              description="Try a wider time range, adjust your filters, or send an execution through the telemetry API."
              action={
                offset > 0 ? <Button onClick={() => setOffset(0)}>Return to first page</Button> : <Button onClick={reset}>Reset filters</Button>
              }
            />
          )}
        </Panel>
      </DataState>
    </>
  );
}
export function RunTable({ runs }: { runs: Run[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Execution</th>
            <th>Agent</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Tokens</th>
            <th>Cost</th>
            <th>Incidents</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                <Link href={`/runs/${r.id}`} className="table-main">
                  <span className="run-icon">
                    <GitBranch size={15} />
                  </span>
                  <div>
                    <strong>{r.name}</strong>
                    <span className="mono">
                      {r.id.slice(0, 8)}
                      {r.synthetic && <Badge value="demo" demo />}
                    </span>
                  </div>
                </Link>
              </td>
              <td>
                <Link href={`/agents/${r.agent_id}`}>
                  {r.agent_name.replace("demo/", "")}
                </Link>
              </td>
              <td>
                <Badge value={r.status} />
              </td>
              <td className="mono">{duration(r.duration_ms)}</td>
              <td className="mono">{number(r.tokens)}</td>
              <td className="mono">{money(r.cost)}</td>
              <td>
                {r.incidents.length ? (
                  <Link
                    className="text-red"
                    href={`/incidents/${r.incidents[0].id}`}
                  >
                    {r.incidents.length} incident
                    {r.incidents.length > 1 ? "s" : ""}
                  </Link>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td className="muted nowrap">{date(r.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function RunDetail({ id }: { id: string }) {
  const query = useData<{ run: Run; spans: Span[] }>(`runs/${id}/trace`);
  const { notify } = useWorkspace();
  const [selected, setSelected] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState("trace");
  const run = query.data?.run,
    spans = query.data?.spans || [];
  const current =
    spans.find((s) => s.id === selected) ||
    spans.find((s) => s.kind === "llm") ||
    spans[0];
  const max = Math.max(1, ...spans.map((s) => s.offset_ms + s.duration_ms));
  const visible = spans.filter((s) => {
    let p = s.parent_span_id;
    const seen = new Set<string>();
    while (p && !seen.has(p)) {
      if (collapsed.has(p)) return false;
      seen.add(p);
      p = spans.find((x) => x.span_id === p)?.parent_span_id;
    }
    return true;
  });
  return (
    <>
      <Back href="/runs">Run explorer</Back>
      <PageHeader
        title={run?.name || "Run details"}
        description="The complete execution story, one span at a time."
        actions={
          run && (
            <>
              <Badge value={run.status} />
              <Button
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(run.id);
                    notify("Run ID copied");
                  } catch {
                    notify(
                      "Clipboard unavailable. Copy the run ID from metadata.",
                      true,
                    );
                  }
                }}
              >
                <Copy size={14} />
                Copy ID
              </Button>
            </>
          )
        }
      />
      <DataState query={query}>
        {run && (
          <>
            {run.synthetic && <DemoNotice />}
            <div className="detail-metrics">
              <Metric
                label="Execution duration"
                value={duration(run.duration_ms)}
              />
              <Metric label="Tokens consumed" value={number(run.tokens)} />
              <Metric label="Estimated cost" value={money(run.cost)} />
              <Metric label="Execution spans" value={number(spans.length)} />
            </div>
            <div className="tabs">
              {[
                ["trace", "Trace waterfall"],
                ["tools", "Tool timeline"],
                ["llm", "LLM invocations"],
                ["errors", "Error events"],
                ["metadata", "Metadata"],
              ].map(([v, t]) => (
                <button
                  className={tab === v ? "active" : ""}
                  key={v}
                  onClick={() => setTab(v)}
                >
                  {t}
                  {v === "errors" && spans.some((s) => s.error) && (
                    <span className="tab-count">
                      {spans.filter((s) => s.error).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {tab === "trace" && (
              <div className="trace-layout">
                <Panel
                  title="Execution trace"
                  subtitle="Nested parent-child spans and relative timing"
                  action={
                    <span className="mono muted small">
                      {spans[0]?.trace_id.slice(0, 16)}…
                    </span>
                  }
                >
                  <div className="waterfall-header">
                    <span>SPAN / OPERATION</span>
                    <div>
                      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
                        <span key={p}>{duration(max * p)}</span>
                      ))}
                    </div>
                  </div>
                  <div className="waterfall-scroll">
                    {visible.map((s) => {
                      const depth = spanDepth(s, spans),
                        children = spans.some(
                          (x) => x.parent_span_id === s.span_id,
                        );
                      return (
                        <div
                          className={`waterfall-row ${current?.id === s.id ? "selected" : ""}`}
                          key={s.id}
                        >
                          <div
                            className="span-name"
                            style={{ paddingLeft: 14 + depth * 18 }}
                          >
                            {children ? (
                              <button
                                aria-label={
                                  collapsed.has(s.span_id)
                                    ? `Expand ${s.name}`
                                    : `Collapse ${s.name}`
                                }
                                onClick={() =>
                                  setCollapsed((prev) => {
                                    const n = new Set(prev);
                                    if (n.has(s.span_id)) n.delete(s.span_id);
                                    else n.add(s.span_id);
                                    return n;
                                  })
                                }
                              >
                                {collapsed.has(s.span_id) ? (
                                  <ChevronRight size={12} />
                                ) : (
                                  <ChevronDown size={12} />
                                )}
                              </button>
                            ) : (
                              <span className="span-spacer" />
                            )}
                            <span className={`span-kind kind-${s.kind}`}>
                              {s.kind === "llm" ? (
                                <Cpu size={13} />
                              ) : s.kind === "tool" ? (
                                <Zap size={13} />
                              ) : (
                                <Bot size={13} />
                              )}
                            </span>
                            <button
                              className="span-select"
                              onClick={() => setSelected(s.id)}
                              title={s.name}
                            >
                              {s.name}
                            </button>
                            {s.status === "failed" && (
                              <TriangleAlert size={12} className="text-red" />
                            )}
                          </div>
                          <button
                            aria-label={`Inspect span ${s.name}`}
                            className="waterfall-track"
                            onClick={() => setSelected(s.id)}
                          >
                            <span
                              className={`waterfall-bar bar-${s.kind} ${s.status === "failed" ? "bar-failed" : ""}`}
                              style={{
                                left: `${(s.offset_ms / max) * 100}%`,
                                width: `${Math.max(0.6, (s.duration_ms / max) * 100)}%`,
                              }}
                            />
                            <span className="bar-duration">
                              {duration(s.duration_ms)}
                            </span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                  <div className="chart-footer">
                    <span>Click a span to inspect its recorded details.</span>
                    <span>{spans.length} spans</span>
                  </div>
                </Panel>
                <Panel
                  title="Span details"
                  subtitle={current?.name || "Select an execution span"}
                >
                  {current ? (
                    <>
                      <div className="key-values">
                        <Row
                          name="Kind"
                          value={<Badge value={current.kind} />}
                        />
                        <Row
                          name="Status"
                          value={<Badge value={current.status} />}
                        />
                        <Row
                          name="Duration"
                          value={duration(current.duration_ms)}
                        />
                        <Row name="Started" value={date(current.started_at)} />
                        <Row
                          name="Span ID"
                          value={
                            <span className="mono">{current.span_id}</span>
                          }
                        />
                        {current.model && (
                          <Row name="Model" value={current.model} />
                        )}
                        {current.kind === "llm" && (
                          <>
                            <Row
                              name="Input tokens"
                              value={number(current.input_tokens)}
                            />
                            <Row
                              name="Output tokens"
                              value={number(current.output_tokens)}
                            />
                            <Row name="Cost" value={money(current.cost)} />
                          </>
                        )}
                      </div>
                      {current.error && (
                        <div className="error-callout">
                          <TriangleAlert size={14} />
                          {current.error}
                        </div>
                      )}
                      <div className="subheading">RECORDED ATTRIBUTES</div>
                      <Json value={current.attributes} />
                    </>
                  ) : (
                    <Empty compact description="No spans recorded." />
                  )}
                </Panel>
              </div>
            )}
            {tab === "tools" && (
              <Panel
                title="Tool execution timeline"
                subtitle="Recorded calls ordered by execution time"
              >
                {spans
                  .filter((s) => s.kind === "tool")
                  .map((s) => (
                    <div className="tool-timeline-row" key={s.id}>
                      <span className="timeline-marker">
                        <Zap size={13} />
                      </span>
                      <div className="grow">
                        <strong>{s.name}</strong>
                        <span className="mono muted small">
                          {date(s.started_at)} · {s.span_id}
                        </span>
                        {s.error && <p className="text-red">{s.error}</p>}
                      </div>
                      <span className="mono small">
                        {duration(s.duration_ms)}
                      </span>
                      <Badge value={s.status} />
                    </div>
                  ))}
                {!spans.some((s) => s.kind === "tool") && (
                  <Empty
                    compact
                    description="No tool invocations were recorded for this run."
                  />
                )}
              </Panel>
            )}
            {tab === "llm" && (
              <div className="llm-grid">
                {spans
                  .filter((s) => s.kind === "llm")
                  .map((s) => (
                    <Panel
                      title={s.name}
                      subtitle={s.model || "Model not recorded"}
                      key={s.id}
                      action={<Cpu size={17} className="text-purple" />}
                    >
                      <div className="key-values">
                        <Row name="Model" value={s.model || "Unavailable"} />
                        <Row
                          name="Input tokens"
                          value={number(s.input_tokens)}
                        />
                        <Row
                          name="Output tokens"
                          value={number(s.output_tokens)}
                        />
                        <Row name="Latency" value={duration(s.duration_ms)} />
                        <Row name="Estimated cost" value={money(s.cost)} />
                      </div>
                      <div className="token-breakdown">
                        <span style={{ flex: Math.max(1, s.input_tokens) }} />
                        <span style={{ flex: Math.max(1, s.output_tokens) }} />
                      </div>
                      <div className="chart-legend token-legend">
                        <span>
                          <i className="legend-green" />
                          Input {number(s.input_tokens)}
                        </span>
                        <span>
                          <i className="legend-purple" />
                          Output {number(s.output_tokens)}
                        </span>
                      </div>
                      <Json value={s.attributes} />
                      <div className="privacy-note">
                        <ShieldIcon />
                        Metadata only. No hidden reasoning is displayed.
                      </div>
                    </Panel>
                  ))}
                {!spans.some((s) => s.kind === "llm") && (
                  <Empty description="No LLM invocations recorded for this run." />
                )}
              </div>
            )}
            {tab === "errors" && (
              <Panel
                title="Error events"
                subtitle="Failures recorded by the monitored execution"
              >
                {spans
                  .filter((s) => s.error)
                  .map((s) => (
                    <div className="error-event" key={s.id}>
                      <TriangleAlert size={18} />
                      <div>
                        <strong>{s.name}</strong>
                        <span>
                          {date(s.started_at)} · span {s.span_id}
                        </span>
                        <pre>{s.error}</pre>
                      </div>
                    </div>
                  ))}
                {!spans.some((s) => s.error) && (
                  <Empty
                    compact
                    title="No errors recorded"
                    description="This run has no recorded error events."
                  />
                )}
              </Panel>
            )}
            {tab === "metadata" && (
              <Panel title="Execution metadata">
                <div className="key-values">
                  <Row
                    name="Run ID"
                    value={<span className="mono">{run.id}</span>}
                  />
                  <Row
                    name="Agent"
                    value={
                      <Link href={`/agents/${run.agent_id}`}>
                        {run.agent_name}
                      </Link>
                    }
                  />
                  <Row name="Environment" value={run.environment} />
                  <Row name="Started at" value={date(run.started_at)} />
                  <Row
                    name="Ended at"
                    value={run.ended_at ? date(run.ended_at) : "Still running"}
                  />
                  <Row
                    name="Telemetry source"
                    value={run.synthetic ? "Synthetic demo" : "Live telemetry"}
                  />
                </div>
                <Json value={run.meta} />
              </Panel>
            )}
            {!!run.incidents.length && (
              <Panel title="Associated incidents">
                {run.incidents.map((i) => (
                  <Link
                    className="incident-row"
                    href={`/incidents/${i.id}`}
                    key={i.id}
                  >
                    <span className={`severity-bar severity-${i.severity}`} />
                    <strong className="grow">{i.title}</strong>
                    <Badge value={i.severity} />
                    <Badge value={i.status} />
                    <ChevronRight size={14} />
                  </Link>
                ))}
              </Panel>
            )}
          </>
        )}
      </DataState>
    </>
  );
}
function ShieldIcon() {
  return <Code2 size={13} />;
}
export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
export function Row({ name, value }: { name: string; value: React.ReactNode }) {
  return (
    <div className="key-value">
      <span>{name}</span>
      <strong>{value}</strong>
    </div>
  );
}
