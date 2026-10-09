"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clipboard,
  Clock3,
  Copy,
  Database,
  Fingerprint,
  FlaskConical,
  FolderKanban,
  KeyRound,
  LockKeyhole,
  Play,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  TriangleAlert,
  Workflow,
  Zap,
} from "lucide-react";
import { Background, ReactFlow, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Agent, Key, Project, Settings } from "@/lib/types";
import { date, label } from "@/lib/format";
import { useAction, useData, useWorkspace } from "./workspace";
import { Badge, DataState, Empty, Field, PageHeader, Panel } from "./common";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";
import { Row } from "./telemetry-pages";
const settingsTabs = [
  ["projects", "Projects", FolderKanban],
  ["keys", "API keys", KeyRound],
  ["agents", "Agent configuration", Bot],
  ["detection", "Detection thresholds", Fingerprint],
  ["providers", "LLM providers", Sparkles],
  ["policies", "Remediation policies", ShieldCheck],
  ["retention", "Data retention", Database],
] as const;
export function SettingsPage() {
  const query = useData<Settings>("settings");
  const { project } = useWorkspace();
  const [tab, setTab] = useState("projects");
  const [form, setForm] = useState<Settings | null>(null);
  const [dirty, setDirty] = useState(false);
  const { act, pending } = useAction();
  useEffect(() => {
    setForm(null);
    setDirty(false);
  }, [project]);
  useEffect(() => {
    if (query.data && !dirty) setForm(query.data);
  }, [query.data, dirty]);
  function change(patch: Partial<Settings>) {
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));
    setDirty(true);
  }
  return (
    <>
      <PageHeader
        title="Settings"
        description="Configure your workspace, integrations, and operational guardrails."
      />
      <div className="settings-layout">
        <nav className="settings-nav">
          {settingsTabs.map(([key, title, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={tab === key ? "active" : ""}
            >
              <Icon size={16} />
              {title}
              <ChevronRight size={13} />
            </button>
          ))}
        </nav>
        <div>
          <DataState query={query}>
            {tab === "projects" && <ProjectsSettings key={project} />}
            {tab === "keys" && <KeysSettings key={project} />}
            {tab === "agents" && <AgentSettings key={project} />}
            {form && (
              <>
                {tab === "detection" && (
                  <Panel
                    title="Detection thresholds"
                    subtitle="Versioned deterministic rules. Changes apply to future evaluations."
                  >
                    <div className="settings-form">
                      <div className="form-grid">
                        {[
                          [
                            "loop_threshold",
                            "Repeated tool calls",
                            "Matching argument and result fingerprints without progress.",
                            3,
                            1000,
                          ],
                          [
                            "token_budget",
                            "Token budget per run",
                            "Combined input and output tokens.",
                            100,
                            100000000,
                          ],
                          [
                            "failure_threshold",
                            "Tool failure threshold",
                            "Failed tool invocations in one run.",
                            2,
                            1000,
                          ],
                          [
                            "stall_seconds",
                            "Stall window (seconds)",
                            "Idle time without spans or heartbeats.",
                            30,
                            86400,
                          ],
                          [
                            "cost_budget",
                            "Cost budget per run (USD)",
                            "Only evaluated when model pricing is known.",
                            0.01,
                            100000,
                          ],
                        ].map(([key, title, hint, min, max]) => (
                          <Field
                            label={String(title)}
                            hint={String(hint)}
                            key={String(key)}
                          >
                            <input
                              type="number"
                              min={Number(min)}
                              max={Number(max)}
                              step={key === "cost_budget" ? ".01" : "1"}
                              required
                              value={
                                form.detection[
                                  key as keyof Settings["detection"]
                                ]
                              }
                              onChange={(e) =>
                                change({
                                  detection: {
                                    ...form.detection,
                                    [String(key)]: Number(e.target.value),
                                  },
                                })
                              }
                            />
                          </Field>
                        ))}
                      </div>
                      <div className="info-callout">
                        <Fingerprint size={16} />
                        <span>
                          Legitimate polling is excluded when explicitly marked.
                          Workflow constraints are configured per agent.
                        </span>
                      </div>
                    </div>
                  </Panel>
                )}
                {tab === "providers" && (
                  <ProviderSettings form={form} change={change} />
                )}
                {tab === "policies" && (
                  <Panel
                    title="Remediation policies"
                    subtitle="Control is a capability, not a consequence of telemetry access."
                  >
                    <div className="settings-form">
                      <div className="policy-header">
                        <ShieldCheck size={24} />
                        <div>
                          <h3>Recommendation-only for real agents</h3>
                          <p>
                            Investigations collect evidence and propose
                            interventions. No monitored application is mutated
                            without a compatible registered adapter.
                          </p>
                        </div>
                        <Badge value="enabled" />
                      </div>
                      <label className="toggle-row">
                        <div>
                          <strong>Allow isolated demo control</strong>
                          <p>
                            Permit explicitly approved cancellation of synthetic
                            simulation runs. Real agents remain
                            recommendation-only.
                          </p>
                        </div>
                        <input
                          aria-label="Allow isolated demo control"
                          type="checkbox"
                          checked={form.allow_demo_control}
                          onChange={(e) =>
                            change({ allow_demo_control: e.target.checked })
                          }
                        />
                      </label>
                      <div className="policy-checks">
                        {[
                          "Explicit approval before execution",
                          "Project authorization and target capability validation",
                          "Idempotent actions and persisted audit history",
                          "Independent recovery observation window",
                        ].map((s) => (
                          <span key={s}>
                            <Check size={14} />
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  </Panel>
                )}
                {tab === "retention" && (
                  <Panel
                    title="Data retention"
                    subtitle="Keep execution history useful, bounded, and intentional."
                  >
                    <div className="settings-form">
                      <Field
                        label="Telemetry retention (days)"
                        hint="Expired runs and spans are pruned hourly. Evidence associated with incidents is preserved for audit history."
                      >
                        <input
                          type="number"
                          min={1}
                          max={3650}
                          required
                          value={form.retention_days}
                          onChange={(e) =>
                            change({ retention_days: Number(e.target.value) })
                          }
                        />
                      </Field>
                      <div className="info-callout">
                        <Database size={17} />
                        <span>
                          Projects, agent identities, API keys, and incident
                          reports are retained. This setting applies to
                          execution telemetry without incident references.
                        </span>
                      </div>
                    </div>
                  </Panel>
                )}
                {["detection", "providers", "policies", "retention"].includes(
                  tab,
                ) && (
                  <div className="settings-save">
                    <span>
                      {dirty
                        ? "You have unsaved changes"
                        : "Configuration is up to date"}
                    </span>
                    <Button
                      variant="primary"
                      disabled={pending || !dirty}
                      onClick={async () => {
                        const result = await act<Settings>(
                          "settings",
                          form,
                          "Project settings saved",
                          "PUT",
                        );
                        if (result) {
                          setForm(result);
                          setDirty(false);
                        }
                      }}
                    >
                      {pending ? "Saving…" : "Save changes"}
                    </Button>
                  </div>
                )}
              </>
            )}
          </DataState>
        </div>
      </div>
    </>
  );
}
function ProjectsSettings() {
  const { projects, setProject } = useWorkspace();
  const { act, pending } = useAction();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  return (
    <>
      <Panel
        title="Project management"
        subtitle="Each project has isolated agents, traces, incidents, and API keys."
        action={
          <Button onClick={() => setOpen(true)}>
            <Plus size={14} />
            New project
          </Button>
        }
      >
        {projects.map((p) => (
          <div className="project-row" key={p.id}>
            <span className="project-icon">
              <FolderKanban size={19} />
            </span>
            <div className="grow">
              <strong>{p.name}</strong>
              <span>{p.description || "Agent observability project"}</span>
              <code>{p.id}</code>
            </div>
            <Button onClick={() => setProject(p.id)}>
              Switch to project <ArrowRight size={13} />
            </Button>
          </div>
        ))}
      </Panel>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Create a project"
        description="A separate boundary for telemetry, agents, API keys, and operational settings."
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const p = await act<Project>(
              "projects",
              { name, description },
              "Project created",
            );
            if (p) {
              setProject(p.id);
              setOpen(false);
              setName("");
              setDescription("");
            }
          }}
        >
          <Field label="Project name">
            <input
              required
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              placeholder="Production agents"
            />
          </Field>
          <Field label="Description">
            <textarea
              value={description}
              maxLength={1000}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What will you observe in this project?"
            />
          </Field>
          <div className="form-actions">
            <Button type="button" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={pending}>
              Create project
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
function KeysSettings() {
  const query = useData<Key[]>("api-keys");
  const { act, pending } = useAction();
  const { notify } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [revealed, setRevealed] = useState("");
  const [revoke, setRevoke] = useState<Key | null>(null);
  return (
    <>
      <Panel
        title="API key management"
        subtitle="Project-scoped keys. Stored as SHA-256 digests; shown only once."
        action={
          <Button
            onClick={() => {
              setRevealed("");
              setOpen(true);
            }}
          >
            <Plus size={14} />
            Create API key
          </Button>
        }
      >
        <DataState query={query}>
          {query.data?.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Key prefix</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {query.data.map((k) => (
                    <tr key={k.id}>
                      <td>
                        <KeyRound size={14} className="inline-icon" />
                        {k.name}
                      </td>
                      <td className="mono">{k.prefix}••••••••</td>
                      <td>
                        <Badge value={k.revoked ? "revoked" : "active"} />
                      </td>
                      <td className="muted">{date(k.created_at)}</td>
                      <td>
                        <Button
                          variant="danger"
                          disabled={k.revoked || pending}
                          onClick={() => setRevoke(k)}
                        >
                          <Trash2 size={13} />
                          Revoke
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              compact
              title="No API keys yet"
              description="Create a key to register agents and ingest telemetry into this project."
            />
          )}
        </DataState>
      </Panel>
      <div className="info-callout">
        <LockKeyhole size={17} />
        <span>
          API keys can ingest and read project telemetry. Dashboard
          administration, investigation control, and remediation require
          dashboard authorization.
        </span>
      </div>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          setOpen(v);
          if (!v) setRevealed("");
        }}
        title={revealed ? "Save your API key" : "Create an API key"}
        description={
          revealed
            ? "This is the only time the full key is shown. Store it securely and use it in your SDK configuration."
            : "Name the key for the integration or environment that will use it."
        }
      >
        {revealed ? (
          <>
            <div className="secret-reveal">
              <code>{revealed}</code>
              <Button
                aria-label="Copy API key"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(revealed);
                    notify("API key copied");
                  } catch {
                    notify(
                      "Clipboard unavailable. Copy the displayed key manually.",
                      true,
                    );
                  }
                }}
              >
                <Copy size={14} />
              </Button>
            </div>
            <div className="form-actions">
              <Button
                variant="primary"
                onClick={() => {
                  setOpen(false);
                  setRevealed("");
                }}
              >
                I saved the key
              </Button>
            </div>
          </>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const result = await act<{ key: string }>(
                "api-keys",
                { name },
                "API key created",
              );
              if (result) {
                setRevealed(result.key);
                setName("");
              }
            }}
          >
            <Field label="Key name">
              <input
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="development-sdk"
              />
            </Field>
            <div className="form-actions">
              <Button type="button" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={pending}>
                Create key
              </Button>
            </div>
          </form>
        )}
      </Dialog>
      <Dialog
        open={!!revoke}
        onOpenChange={(v) => {
          if (!v) setRevoke(null);
        }}
        title="Revoke this API key?"
        description="New requests using this key will be rejected immediately. Existing telemetry remains available."
      >
        <p className="confirmation-body">
          Key: <strong>{revoke?.name}</strong>
        </p>
        <div className="form-actions">
          <Button onClick={() => setRevoke(null)}>Keep key</Button>
          <Button
            variant="danger"
            disabled={pending}
            onClick={async () => {
              if (!revoke) return;
              await act(
                `api-keys/${revoke.id}`,
                {},
                "API key revoked",
                "DELETE",
              );
              setRevoke(null);
            }}
          >
            Revoke key
          </Button>
        </div>
      </Dialog>
    </>
  );
}
function AgentSettings() {
  const query = useData<Agent[]>("agents");
  const { act, pending } = useAction();
  const { notify } = useWorkspace();
  const [selected, setSelected] = useState("");
  const [value, setValue] = useState("");
  useEffect(() => {
    if (query.data?.length && !selected) {
      setSelected(query.data[0].id);
      const config = { ...query.data[0].configuration };
      delete config.control_adapter;
      setValue(JSON.stringify(config, null, 2));
    }
  }, [query.data, selected]);
  return (
    <Panel
      title="Agent configuration"
      subtitle="Declared workflow constraints and expected execution behavior."
    >
      <DataState query={query}>
        {query.data?.length ? (
          <div className="settings-form">
            <Field label="Agent">
              <select
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  const config = {
                    ...query.data?.find((a) => a.id === e.target.value)
                      ?.configuration,
                  };
                  delete config.control_adapter;
                  setValue(JSON.stringify(config, null, 2));
                }}
              >
                {query.data.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Configuration (JSON)"
              hint="Supported fields: allowed_tools (string array), expected_duration_seconds (number). Other application metadata may also be recorded."
            >
              <textarea
                className="code-editor"
                rows={9}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                spellCheck={false}
              />
            </Field>
            <div className="form-actions">
              <Button
                variant="primary"
                disabled={pending}
                onClick={async () => {
                  try {
                    const configuration = JSON.parse(value);
                    if (
                      !configuration ||
                      Array.isArray(configuration) ||
                      typeof configuration !== "object"
                    )
                      throw Error("Configuration must be a JSON object");
                    await act(
                      `agents/${selected}`,
                      { configuration },
                      "Agent configuration saved",
                      "PATCH",
                    );
                  } catch (e) {
                    notify(
                      e instanceof Error ? e.message : "Invalid JSON",
                      true,
                    );
                  }
                }}
              >
                Save agent configuration
              </Button>
            </div>
          </div>
        ) : (
          <Empty
            compact
            title="No agents registered"
            description="Register an agent before configuring its workflow constraints."
            action={
              <Button asChild>
                <Link href="/agents">
                  Register agent <ArrowRight size={14} />
                </Link>
              </Button>
            }
          />
        )}
      </DataState>
    </Panel>
  );
}
function ProviderSettings({
  form,
  change,
}: {
  form: Settings;
  change: (patch: Partial<Settings>) => void;
}) {
  const status = useData<{
    credential_configured: boolean;
    allowed_hosts: string[];
  }>("settings/provider-status");
  return (
    <Panel
      title="LLM provider settings"
      subtitle="A deterministic investigator is always available without paid APIs."
    >
      <div className="settings-form">
        <Field label="Investigation provider">
          <select
            value={form.provider}
            onChange={(e) =>
              change({ provider: e.target.value as Settings["provider"] })
            }
          >
            <option value="deterministic">
              Deterministic · Local LangGraph workflow
            </option>
            <option value="openai_compatible">
              OpenAI-compatible · Optional suggestions
            </option>
          </select>
        </Field>
        {form.provider === "openai_compatible" && (
          <>
            <Field
              label="Provider base URL"
              hint={`HTTPS only. Server allowlist: ${status.data?.allowed_hosts.join(", ") || "loading…"}`}
            >
              <input
                type="url"
                value={form.provider_base_url}
                onChange={(e) => change({ provider_base_url: e.target.value })}
              />
            </Field>
            <Field label="Model">
              <input
                maxLength={100}
                value={form.provider_model}
                onChange={(e) => change({ provider_model: e.target.value })}
              />
            </Field>
            <Row
              name="Server credential"
              value={
                status.data?.credential_configured
                  ? "Configured securely"
                  : "Not configured · deterministic fallback"
              }
            />
          </>
        )}
        <div className="provider-card">
          <span className="investigation-icon">
            <Sparkles size={21} />
          </span>
          <div>
            <h3>Evidence-based investigator</h3>
            <p>
              Five bounded workflow stages. Model suggestions are marked
              unverified and must reference collected evidence. Deterministic
              findings remain primary.
            </p>
          </div>
          <Badge value="available" />
        </div>
        <div className="info-callout">
          <LockKeyhole size={17} />
          <span>
            Configure AGENTSCOPE_LLM_API_KEY securely on the API server to
            enable the optional provider. No credentials are stored by this
            form. Calls are bounded to one request, 600 output tokens, and a
            10-second timeout; failure falls back to the local report.
          </span>
        </div>
      </div>
    </Panel>
  );
}
const scenarios = [
  {
    id: "tool_loop",
    title: "Tool-call loop",
    icon: RefreshCw,
    color: "green",
    description:
      "An agent repeats the same search, with identical arguments and result fingerprints, without making progress.",
    signal: "8 repeated tool calls · no progress",
    severity: "high",
  },
  {
    id: "token_budget",
    title: "Token budget overrun",
    icon: CircleDollarSign,
    color: "purple",
    description:
      "A large context drives recorded token consumption beyond the configured per-run budget.",
    signal: "22k input tokens · budget violation",
    severity: "high",
  },
  {
    id: "tool_failure",
    title: "Tool failure storm",
    icon: TriangleAlert,
    color: "orange",
    description:
      "Repeated upstream rate limits cause failed tool calls and a failed agent execution.",
    signal: "5 HTTP 429 failures · retry storm",
    severity: "critical",
  },
  {
    id: "stalled",
    title: "Stalled execution",
    icon: Clock3,
    color: "blue",
    description:
      "An active run stops reporting progress and misses its configured heartbeat window.",
    signal: "12 minutes idle · no heartbeat",
    severity: "medium",
  },
  {
    id: "unexpected_workflow",
    title: "Unexpected workflow",
    icon: Workflow,
    color: "purple",
    description:
      "A recorded tool invocation falls outside the agent’s declared workflow allowlist.",
    signal: "Unlisted tool · workflow violation",
    severity: "medium",
  },
  {
    id: "healthy",
    title: "Healthy baseline",
    icon: ShieldCheck,
    color: "green",
    description:
      "A normal execution with successful tool calls and bounded model usage, for comparison.",
    signal: "Successful tools · within budget",
    severity: "healthy",
  },
];
export function SimulationPage() {
  const [seed, setSeed] = useState(42);
  const [baseline, setBaseline] = useState(true);
  const [running, setRunning] = useState("");
  const [result, setResult] = useState<{
    run_ids: string[];
    scenario: string;
    seed: number;
  } | null>(null);
  const { act } = useAction();
  async function trigger(scenario: string) {
    setRunning(scenario);
    const data = await act<typeof result>(
      "simulations",
      { scenario, seed, include_baseline: baseline },
      "Synthetic scenario recorded. Telemetry and detector results are now available.",
    );
    if (data) setResult(data);
    setRunning("");
  }
  return (
    <>
      <PageHeader
        title="Simulation lab"
        description="Reproduce the failure. Understand the signal. Practice the response."
        actions={
          <span className="lab-label">
            <FlaskConical size={14} />
            DEMO ENVIRONMENT
          </span>
        }
      />
      <div className="lab-banner">
        <span className="lab-banner-icon">
          <FlaskConical size={26} />
        </span>
        <div>
          <h2>Real pipeline. Synthetic telemetry.</h2>
          <p>
            Each scenario emits reproducible events through the same ingestion,
            storage, detection, and investigation paths as live agents. Every
            generated agent, run, and report is labeled as demo data.
          </p>
        </div>
        <span className="lab-badge">NO EXTERNAL APIS</span>
      </div>
      <Panel
        title="From signal to resolution"
        subtitle="Explore the complete incident lifecycle without touching a real agent."
      >
        <Pipeline />
      </Panel>
      <div className="simulation-controls">
        <div>
          <h2>Choose a scenario</h2>
          <p>
            Same seed, same execution pattern. IDs and timestamps are generated
            for each run.
          </p>
        </div>
        <div className="lab-options">
          <label>
            Seed{" "}
            <input
              type="number"
              aria-label="Simulation seed"
              min={0}
              max={2147483647}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={baseline}
              onChange={(e) => setBaseline(e.target.checked)}
            />
            Include 24 healthy demo runs
          </label>
        </div>
      </div>
      <div className="scenario-grid">
        {scenarios.map((s) => (
          <section className="scenario-card panel" key={s.id}>
            <div className="scenario-top">
              <span className={`scenario-icon ${s.color}`}>
                <s.icon size={23} />
              </span>
              <Badge value={s.severity} />
            </div>
            <h2>{s.title}</h2>
            <p>{s.description}</p>
            <div className="scenario-signal">
              <Fingerprint size={13} />
              {s.signal}
            </div>
            <Button
              className="scenario-button"
              disabled={
                !!running ||
                !Number.isInteger(seed) ||
                seed < 0 ||
                seed > 2147483647
              }
              onClick={() => trigger(s.id)}
            >
              {running === s.id ? (
                <>
                  <RefreshCw className="spin" size={14} />
                  Generating telemetry…
                </>
              ) : (
                <>
                  <Play size={14} />
                  Run scenario
                  <ArrowUpRight size={14} />
                </>
              )}
            </Button>
          </section>
        ))}
      </div>
      {result && (
        <div className="simulation-result" role="status">
          <Check size={22} />
          <div className="grow">
            <h3>Scenario recorded: {label(result.scenario)}</h3>
            <p>
              {result.run_ids.length} synthetic runs persisted · seed{" "}
              {result.seed}.{" "}
              {result.scenario === "healthy"
                ? "Review the baseline in the run explorer."
                : "Open the incident center to begin an evidence-based investigation."}
            </p>
          </div>
          <Button asChild>
            <Link href={`/runs/${result.run_ids[result.run_ids.length - 1]}`}>
              Inspect run <ArrowUpRight size={13} />
            </Link>
          </Button>
          <Button variant="primary" asChild>
            <Link href="/incidents">
              View incidents <ArrowRight size={14} />
            </Link>
          </Button>
        </div>
      )}
      <div className="lab-footnote">
        <ShieldCheck size={15} />
        <span>
          Simulation actions only control isolated demo runs. Real agent
          remediation remains recommendation-only.
        </span>
        <Link href="/settings">
          Manage policies <ArrowUpRight size={12} />
        </Link>
      </div>
    </>
  );
}
function Pipeline() {
  const nodes: Node[] = [
    "Emit telemetry",
    "Persist spans",
    "Detect anomaly",
    "Investigate",
    "Verify recovery",
  ].map((label, i) => ({
    id: `${i}`,
    position: { x: i * 180, y: 10 },
    data: { label: `${String(i + 1).padStart(2, "0")}  ${label}` },
    className: `pipeline-node ${i === 0 ? "pipeline-first" : ""}`,
    draggable: false,
    selectable: false,
  }));
  const edges: Edge[] = [0, 1, 2, 3].map((i) => ({
    id: `${i}`,
    source: `${i}`,
    target: `${i + 1}`,
    type: "smoothstep",
    style: { stroke: "#657954" },
  }));
  return (
    <div
      className="pipeline"
      aria-label="Pipeline: emit telemetry, persist spans, detect anomaly, investigate, verify recovery"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        nodesDraggable={false}
        nodesConnectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#30372e" gap={20} />
      </ReactFlow>
    </div>
  );
}
