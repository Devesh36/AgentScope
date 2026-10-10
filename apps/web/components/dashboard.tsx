"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CheckCheck,
  CircleDollarSign,
  Cpu,
  FlaskConical,
  Play,
  ShieldAlert,
  Sparkles,
  Terminal,
  TriangleAlert,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useQueryClient } from "@tanstack/react-query";
import type { Metrics } from "@/lib/types";
import { duration, money, number, relative, time } from "@/lib/format";
import { useData, useWorkspace } from "./workspace";
import {
  Badge,
  DataState,
  DemoNotice,
  Empty,
  PageHeader,
  Panel,
} from "./common";
import { Button } from "./ui/button";
import {
  AgentsPage,
  AgentDetail,
  RunsPage,
  RunDetail,
} from "./telemetry-pages";
import {
  IncidentsPage,
  IncidentDetail,
  InvestigationsPage,
  InvestigationDetail,
} from "./incident-pages";
import { SettingsPage, SimulationPage } from "./settings-pages";
export function Dashboard() {
  const segments = usePathname().split("/").filter(Boolean);
  if (segments[0] === "agents")
    return segments[1] ? <AgentDetail id={segments[1]} /> : <AgentsPage />;
  if (segments[0] === "runs")
    return segments[1] ? <RunDetail id={segments[1]} /> : <RunsPage />;
  if (segments[0] === "incidents")
    return segments[1] ? (
      <IncidentDetail id={segments[1]} />
    ) : (
      <IncidentsPage />
    );
  if (segments[0] === "investigations")
    return segments[1] ? (
      <InvestigationDetail id={segments[1]} />
    ) : (
      <InvestigationsPage />
    );
  if (segments[0] === "settings") return <SettingsPage />;
  if (segments[0] === "simulation") return <SimulationPage />;
  if (segments.length && !(segments.length === 1 && segments[0] === "dashboard"))
    return (
      <Empty
        title="Page not found"
        description="This page doesn’t exist in your workspace."
        action={
          <Button asChild>
            <Link href="/dashboard">Back to overview</Link>
          </Button>
        }
      />
    );
  return <Overview />;
}
function Overview() {
  const { hours, source, project, connected } = useWorkspace();
  const client = useQueryClient();
  const query = useData<Metrics>(
    `metrics/overview?hours=${hours}${source === "all" ? "" : `&synthetic=${source === "demo"}`}`,
  );
  const data = query.data;
  return (
    <>
      <PageHeader
        title="Overview"
        description="A clear view of your agents. From execution to resolution."
        filters
        actions={
          <>
            <Button
              onClick={() =>
                client.invalidateQueries({
                  predicate: (q) => q.queryKey[0] === project,
                })
              }
            >
              <Activity size={14} />
              Refresh
            </Button>
            <Button variant="primary" asChild>
              <Link href="/agents">
                <Bot size={15} />
                Connect an agent
              </Link>
            </Button>
          </>
        }
      />
      <DataState query={query}>
        {data && (
          <>
            {!!data.synthetic_runs && (
              <DemoNotice count={data.synthetic_runs} />
            )}
            {!!data.watch_sessions?.length && (
              <Panel title="Local project monitoring" subtitle="Runtime telemetry from applications launched with AgentScope">
                <div className="watch-sessions">
                  {data.watch_sessions.map((session) => <div className="watch-session" key={session.agent_id}><span className={`status-dot ${session.status === "monitoring" || session.status === "waiting" ? "green" : "amber"}`} /><div><strong>{session.repository}</strong><p>{session.status === "monitoring" ? "Application running · capturing supported LLM calls" : session.status === "waiting" ? "Waiting for activity · launch your app with agentscope run" : session.status === "stopped" ? "Watch stopped · recorded activity is preserved" : "Watch disconnected · restart agentscope watch"}</p></div><code>{session.status}</code></div>)}
                </div>
              </Panel>
            )}
            <div className="overview-status">
              <div>
                <span
                  className={`status-dot ${data.active_incidents ? "amber" : "green"}`}
                />
                <strong>
                  {data.active_incidents
                    ? `${data.active_incidents} incident${data.active_incidents === 1 ? "" : "s"} need attention`
                    : data.total_runs
                      ? "Your agents are operating normally"
                      : "Ready to receive your first trace"}
                </strong>
                <span>
                  {data.total_runs
                    ? `${number(data.total_runs)} runs observed in the selected window`
                    : "Connect an agent or explore a reproducible simulation"}
                </span>
              </div>
              <span className="muted small">
                {connected ? "Updated live" : "Updates reconnecting"}
              </span>
            </div>
            <div className="metric-grid">
              {[
                [
                  "Registered agents",
                  number(data.registered_agents),
                  Bot,
                  "In this project",
                  "neutral",
                ],
                [
                  "Active runs",
                  number(data.active_runs),
                  Activity,
                  "Currently executing",
                  "green",
                ],
                [
                  "Failed runs",
                  number(data.failed_runs),
                  TriangleAlert,
                  "In selected window",
                  data.failed_runs ? "red" : "neutral",
                ],
                [
                  "Success rate",
                  data.success_rate == null ? "—" : `${data.success_rate}%`,
                  CheckCheck,
                  "Completed / terminal runs",
                  "green",
                ],
                [
                  "Tokens consumed",
                  number(data.tokens),
                  Cpu,
                  `${number(data.input_tokens)} in · ${number(data.output_tokens)} out`,
                  "neutral",
                ],
                [
                  "Estimated cost",
                  money(data.cost),
                  CircleDollarSign,
                  data.cost == null
                    ? data.llm_calls ? "Pricing or usage is incomplete" : "No observed model usage"
                    : "Recorded model list pricing",
                  "neutral",
                ],
                ["LLM calls", number(data.llm_calls ?? 0), Sparkles, `${number(data.llm_errors ?? 0)} failed calls`, "neutral"],
                ["Unsupported claims", data.unsupported_claims == null ? "Not evaluated" : number(data.unsupported_claims), ShieldAlert, data.grounding_evaluations ? `${number(data.grounding_evaluations)} application grounding checks` : "Requires reference-based evaluation", "neutral"],
              ].map(([title, value, Icon, note, color]) => {
                const I = Icon as typeof Bot;
                return (
                  <div className="metric-card" key={String(title)}>
                    <div className="metric-label">
                      {String(title)}
                      <I size={15} />
                    </div>
                    <div className={`metric-value text-${color} ${value === "Not evaluated" || value === "Unavailable" ? "metric-value-label" : ""}`}>
                      {String(value)}
                    </div>
                    <div className="metric-note">{String(note)}</div>
                  </div>
                );
              })}
            </div>
            {!data.total_runs && (
              <div className="onboarding-banner">
                <div className="onboarding-icon">
                  <Waymark />
                </div>
                <div>
                  <h2>Your observability starts here.</h2>
                  <p>
                    Connect your first agent for live telemetry, or take the
                    platform for a spin with clearly labeled demo data.
                  </p>
                </div>
                <Button variant="primary" asChild>
                  <Link href="/simulation">
                    <FlaskConical size={15} />
                    Explore demo
                  </Link>
                </Button>
              </div>
            )}
            <div className="charts-grid">
              <Panel
                title="Token consumption"
                subtitle="Recorded input and output tokens over time"
                action={
                  <div className="chart-legend">
                    <span>
                      <i className="legend-green" />
                      Input tokens
                    </span>
                    <span>
                      <i className="legend-purple" />
                      Output tokens
                    </span>
                  </div>
                }
              >
                <div className="chart-summary">
                  <strong>{number(data.tokens)}</strong>
                  <span>total tokens</span>
                  <span className="chart-window">
                    LAST {hours < 24 ? `${hours}H` : `${hours / 24}D`}
                  </span>
                </div>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={data.series}
                      margin={{ top: 8, right: 18, left: -20, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient
                          id="tokensIn"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="#b5e88f"
                            stopOpacity={0.2}
                          />
                          <stop
                            offset="100%"
                            stopColor="#b5e88f"
                            stopOpacity={0}
                          />
                        </linearGradient>
                        <linearGradient
                          id="tokensOut"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="#a295e4"
                            stopOpacity={0.15}
                          />
                          <stop
                            offset="100%"
                            stopColor="#a295e4"
                            stopOpacity={0}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        vertical={false}
                        stroke="#252b31"
                        strokeDasharray="3 5"
                      />
                      <XAxis
                        dataKey="at"
                        tickFormatter={time}
                        minTickGap={55}
                        tick={{ fill: "#737f89", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tickFormatter={number}
                        tick={{ fill: "#737f89", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        labelFormatter={(v) => time(String(v))}
                      />
                      <Area
                        isAnimationActive={false}
                        type="monotone"
                        dataKey="input_tokens"
                        name="Input tokens"
                        stroke="#b5e88f"
                        strokeWidth={2}
                        fill="url(#tokensIn)"
                      />
                      <Area
                        isAnimationActive={false}
                        type="monotone"
                        dataKey="output_tokens"
                        name="Output tokens"
                        stroke="#a295e4"
                        strokeWidth={2}
                        fill="url(#tokensOut)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                  {!data.total_runs && (
                    <div className="chart-empty">Awaiting telemetry</div>
                  )}
                </div>
                <div className="chart-footer">
                  <span>
                    Usage is aggregated from persisted execution spans.
                  </span>
                  <Link href="/runs">
                    Explore runs <ArrowUpRight size={13} />
                  </Link>
                </div>
              </Panel>
              <Panel
                title="Tool error trends"
                subtitle="Failed tool calls across your agents"
                action={
                  <span className="badge badge-neutral">
                    <Zap size={11} />
                    Tools
                  </span>
                }
              >
                <div className="chart-summary">
                  <strong>
                    {data.tool_calls
                      ? `${((data.tool_errors / data.tool_calls) * 100).toFixed(1)}%`
                      : "—"}
                  </strong>
                  <span>error rate</span>
                </div>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={data.series}
                      margin={{ top: 8, right: 18, left: -25, bottom: 0 }}
                    >
                      <CartesianGrid
                        vertical={false}
                        stroke="#252b31"
                        strokeDasharray="3 5"
                      />
                      <XAxis
                        dataKey="at"
                        minTickGap={70}
                        tickFormatter={time}
                        tick={{ fill: "#737f89", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: "#737f89", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        labelFormatter={(v) => time(String(v))}
                      />
                      <Line
                        isAnimationActive={false}
                        type="monotone"
                        dataKey="tool_errors"
                        name="Failed tool calls"
                        stroke="#eaa58d"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                  {!data.tool_calls && (
                    <div className="chart-empty">Awaiting tool calls</div>
                  )}
                </div>
                <div className="chart-footer">
                  <span>
                    {number(data.tool_errors)} errors /{" "}
                    {number(data.tool_calls)} calls
                  </span>
                  <span className="legend-inline">
                    <i className="legend-orange" />
                    Tool errors
                  </span>
                </div>
              </Panel>
            </div>
            <div className="two-col">
              <Panel
                title="Agent health"
                subtitle={`${data.agents.length} registered agents in this project`}
                action={
                  <Link className="text-link" href="/agents">
                    View agents <ArrowUpRight size={13} />
                  </Link>
                }
              >
                {data.agents.length ? (
                  <div className="agent-health-list">
                    {data.agents.slice(0, 4).map((a) => (
                      <Link
                        href={`/agents/${a.id}`}
                        key={a.id}
                        className="health-row"
                      >
                        <span className="agent-icon">
                          <Bot size={17} />
                        </span>
                        <div className="grow">
                          <strong>{a.name.replace("demo/", "")}</strong>
                          <span>
                            {a.framework}{" "}
                            <span className="dot-separator">·</span>{" "}
                            {a.environment}
                          </span>
                        </div>
                        <div className="health-success">
                          <strong>
                            {a.success_rate == null
                              ? "—"
                              : `${a.success_rate}%`}
                          </strong>
                          <span>success rate</span>
                        </div>
                        <Badge value={a.status} />
                      </Link>
                    ))}
                  </div>
                ) : (
                  <Empty
                    compact
                    title="No agents connected"
                    description="Register an agent to begin monitoring its health."
                    action={
                      <Link className="text-link" href="/agents">
                        Connect your first agent <ArrowRight size={14} />
                      </Link>
                    }
                  />
                )}
              </Panel>
              <Panel
                title="Active incidents"
                subtitle="Signals that deserve a closer look"
                action={
                  <Link className="text-link" href="/incidents">
                    View all <ArrowUpRight size={13} />
                  </Link>
                }
              >
                {data.incidents.length ? (
                  <div className="incident-list">
                    {data.incidents.map((i) => (
                      <Link
                        key={i.id}
                        href={`/incidents/${i.id}`}
                        className="incident-row"
                      >
                        <span
                          className={`severity-bar severity-${i.severity}`}
                        />
                        <div className="grow">
                          <strong>{i.title}</strong>
                          <span>
                            {i.agent_name.replace("demo/", "")} ·{" "}
                            {relative(i.created_at)}
                          </span>
                        </div>
                        <Badge value={i.severity} />
                        <ArrowUpRight size={14} className="muted" />
                      </Link>
                    ))}
                  </div>
                ) : (
                  <Empty
                    compact
                    title="No active incidents"
                    description="The detection engine is watching for unusual behavior."
                    action={
                      <span className="muted small">
                        <ShieldAlert size={13} /> Five deterministic detectors
                      </span>
                    }
                  />
                )}
              </Panel>
            </div>
            <div className="two-col">
              <Panel
                title="Recent investigations"
                subtitle="Evidence, explanations, and a path forward"
                action={
                  <Link className="text-link" href="/investigations">
                    View all <ArrowUpRight size={13} />
                  </Link>
                }
              >
                {data.investigations.length ? (
                  data.investigations.map((i) => (
                    <Link
                      className="investigation-row"
                      href={`/investigations/${i.id}`}
                      key={i.id}
                    >
                      <span className="investigation-icon">
                        <Sparkles size={16} />
                      </span>
                      <div className="grow">
                        <strong>{i.incident_title}</strong>
                        <span>
                          {i.phase} · {relative(i.created_at)}
                        </span>
                      </div>
                      <Badge value={i.status} />
                    </Link>
                  ))
                ) : (
                  <Empty
                    compact
                    title="The evidence will lead the way"
                    description="Start an investigation from an incident to gather evidence and evaluate possible causes."
                  />
                )}
              </Panel>
              <Panel
                title="Execution pulse"
                subtitle="Recent activity across your workspace"
                action={
                  <Link className="text-link" href="/runs">
                    All runs <ArrowUpRight size={13} />
                  </Link>
                }
              >
                {data.recent_runs.length ? (
                  data.recent_runs.map((r) => (
                    <Link
                      href={`/runs/${r.id}`}
                      className="pulse-row"
                      key={r.id}
                    >
                      <span
                        className={`status-dot ${r.status === "failed" ? "red" : r.status === "running" ? "amber" : "green"}`}
                      />
                      <div className="grow">
                        <strong>{r.agent_name.replace("demo/", "")}</strong>
                        <span>{r.name}</span>
                      </div>
                      <span className="mono muted small">
                        {duration(r.duration_ms)}
                      </span>
                      <Badge value={r.status} />
                    </Link>
                  ))
                ) : (
                  <Empty
                    compact
                    title="Waiting for the first run"
                    description="Execution events appear here as they arrive."
                  />
                )}
              </Panel>
            </div>
            <div className="overview-footnote">
              <span>
                <Activity size={13} />
                Metrics calculated from stored telemetry · Updated{" "}
                {time(data.updated_at)}
              </span>
              <span>
                P95 latency <strong>{duration(data.latency_p95)}</strong>{" "}
                <span className="dot-separator">·</span>{" "}
                {number(data.completed_runs)} completed runs
              </span>
            </div>
          </>
        )}
      </DataState>
    </>
  );
}
function Waymark() {
  return <Terminal size={25} />;
}
const tooltipStyle = {
  background: "#171c22",
  border: "1px solid #303842",
  borderRadius: 8,
  color: "#e1e7ee",
  fontSize: 12,
};
