import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Activity, ArrowLeft, ArrowRight, BookOpen, GitBranch, Radar, ShieldCheck, Waypoints } from "lucide-react";
import { TerminalTour } from "@/components/terminal-tour";
import { DocCode } from "@/components/doc-code";
import "../landing.css";
import "./docs.css";

export const metadata: Metadata = {
  title: "Documentation · AgentScope",
  description: "Get started with AgentScope: run the local workspace, investigate incidents with the CLI, and instrument your Python agents.",
};

const repository = "https://github.com/Devesh36/AgentScope";
const sections = [
  ["overview", "What is AgentScope?"],
  ["terminal-tour", "Terminal tour"],
  ["chat", "Configure the assistant"],
  ["watch", "Monitor your project"],
  ["quickstart", "Run locally"],
  ["cli", "Connect the CLI"],
  ["demo", "Your first investigation"],
  ["sdk", "Instrument an agent"],
  ["interfaces", "API & storage"],
  ["troubleshooting", "Troubleshooting"],
];

export default function DocumentationPage() {
  return (
    <main className="landing docs-page">
      <a className="landing-skip" href="#overview">Skip to documentation</a>
      <header className="landing-nav">
        <Link href="/" className="landing-brand" aria-label="AgentScope home"><span><Activity size={21} /></span>AgentScope</Link>
        <nav aria-label="Site navigation"><Link href="/">Home</Link><Link href="/docs" aria-current="page">Documentation</Link></nav>
        <a href={repository} className="landing-nav-cta">View source <ArrowRight size={15} /></a>
      </header>
      <div className="docs-layout">
        <aside className="docs-sidebar">
          <span className="docs-sidebar-title"><BookOpen size={15} /> GETTING STARTED</span>
          <nav aria-label="Documentation sections">{sections.map(([id, label], index) => <a href={`#${id}`} key={id}><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{label}</a>)}</nav>
          <a className="docs-source-link" href={`${repository}/tree/main/docs`}>Technical guides <ArrowRight size={14} /></a>
        </aside>
        <article className="docs-content">
          <div className="docs-intro">
            <span className="landing-kicker">AGENTSCOPE DOCUMENTATION</span>
            <h1>Understand every run.<br /><span>Start here.</span></h1>
            <p>A practical guide to observing your agents, investigating the unexpected, and finding your next step in the evidence.</p>
            <div className="docs-meta"><span>Python 3.12+</span><span>Node.js 24</span><span>Configure a model for REPL chat</span></div>
          </div>

          <section id="overview" className="docs-section">
            <span className="docs-section-number">01 / OVERVIEW</span><h2>What is AgentScope?</h2>
            <p>AgentScope is a self-hosted observability workspace for AI agents. The Python SDK records agent executions, tool calls, and model usage. The dashboard and CLI help you inspect those runs, detect incidents, and review investigations grounded in stored traces.</p>
            <div className="docs-capabilities">
              <div><Waypoints size={20} /><h3>Observe</h3><p>Follow nested spans, latency, errors, and observed token usage.</p></div>
              <div><Radar size={20} /><h3>Understand</h3><p>Detect tool loops, budget overruns, failures, and stalled runs.</p></div>
              <div><GitBranch size={20} /><h3>Investigate</h3><p>Connect findings and recommendations to recorded evidence.</p></div>
              <div><ShieldCheck size={20} /><h3>Verify</h3><p>Practice explicit demo intervention and measure follow-up recovery.</p></div>
            </div>
            <div className="docs-note"><strong>You stay in control.</strong><p>Real-agent remediation is recommendation-only. Executable actions are limited to an isolated synthetic demo adapter, require an enabled demo policy, and keep approval separate from execution.</p></div>
          </section>

          <section id="terminal-tour" className="docs-section">
            <span className="docs-section-number">SEE IT IN ACTION / TERMINAL TOUR</span><h2>AgentScope in the terminal</h2>
            <p>Follow ten captured steps, from configuring your assistant to monitoring LLM activity, inspecting failures, investigating an incident, and ending the session.</p>
            <TerminalTour />
          </section>

          <section id="chat" className="docs-section">
            <span className="docs-section-number">START HERE / YOUR ASSISTANT</span><h2>Configure and chat with AgentScope</h2>
            <p>Choose AgentScope&apos;s own assistant model before asking questions. Run <code>agentscope configure</code>, or open the REPL: its first interactive launch guides you through provider, model, and credential setup. Keys are entered in a hidden prompt or referenced through your existing secret environment.</p>
            <DocCode title="Meet your AgentScope assistant">{`agentscope configure
agentscope repl
# Inside the REPL:
model check
Who are you?
What can you help me with?
How do I monitor this project?
watch`}</DocCode>
            <p>Chat supports OpenAI and Codex models, Anthropic/Claude, Gemini, OpenRouter, Groq, DeepSeek, Ollama, and OpenAI-compatible endpoints. Codex and Claude CLI profiles can use their existing CLI login. Your chosen account or local server determines which model identifiers are available.</p>
            <DocCode title="Configure an existing provider credential">{`agentscope configure openai --key-env OPENAI_API_KEY
# Or:
agentscope configure claude --key-env ANTHROPIC_API_KEY
agentscope configure codex`}</DocCode>
            <p>AgentScope answers through your selected model and remembers this session&apos;s conversation. Use <code>model list</code>, <code>model use PROFILE</code>, and <code>chat reset</code> to manage it. Chat explains commands; enter <code>watch</code> and other actions yourself.</p>
            <div className="docs-note"><strong>You choose what the assistant sees.</strong><p>Project context is off by default. After selecting a project, <code>context on</code> sends summary usage, failure, incident, and grounding metrics to the chosen provider. It excludes prompts, trace bodies, source files, and credentials. <code>context off</code> clears that conversation.</p></div>
            <p>This assistant configuration is separate from the models used by your application. Monitoring works without chat; choose monitoring-only mode during setup when needed. Read the <a href={`${repository}/blob/main/docs/chat.md`}>chat and provider guide</a> for configuration and authentication options.</p>
          </section>

          <section id="watch" className="docs-section">
            <span className="docs-section-number">START HERE / LOCAL MONITORING</span><h2>Monitor your existing project</h2>
            <p>Install AgentScope, run it from your application directory, and open a live local dashboard. On macOS or Linux, you need Python 3.12+, Node.js 24 with npm, and uv. Homebrew installation supplies these prerequisites.</p>
            <DocCode title="Watch a Python project">{`uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
cd /path/to/your/project
agentscope watch -- python app.py`}</DocCode>
            <DocCode title="Watch a Node.js project">{`agentscope watch -- npm start`}</DocCode>
            <p>Activate your Python virtual environment first. AgentScope prepares its bundled services on first use, creates a project and private ingestion key, and opens the dashboard with your project selected. Live LLM activity, failures, usage, and detected incidents appear as the application runs.</p>
            <h3>Keep monitoring in the REPL</h3>
            <DocCode title="Start interactive monitoring">{`agentscope repl
# Inside the REPL:
watch
status
incidents
open
# Stop the local services:
stop`}</DocCode>
            <p><code>watch</code> also accepts a directory, and <code>monitor .</code> is an alias. Monitoring continues in the background while you inspect the workspace. Start your application from another terminal in the same directory:</p>
            <DocCode title="Launch into a running watcher">{`agentscope run -- python app.py`}</DocCode>
            <div className="docs-note"><strong>What automatic monitoring captures</strong><p>Python OpenAI chat completions, Responses, and Anthropic Messages create calls, including async and streamed calls; Node.js fetch-based OpenAI/Anthropic-compatible endpoints. Applications must be launched through watch/run. Tool and whole-agent boundaries, unsupported providers, and other languages use SDK or OTLP instrumentation.</p></div>
            <p>Automatic telemetry includes metadata and excludes prompts, generated content, and provider credentials. Unsupported claims remain <strong>Not evaluated</strong> until your application supplies reference-based grounding checks. Missing usage keeps cost unavailable.</p>
            <p>Ctrl+C stops CLI watch services; <code>stop</code> or <code>exit</code> stops a REPL watcher. Recorded activity lives outside your project in your private user workspace and is restored on the next watch. Read the <a href={`${repository}/blob/main/docs/watch.md`}>full watch guide</a> for options and integration details.</p>
          </section>

          <section id="quickstart" className="docs-section">
            <span className="docs-section-number">02 / LOCAL WORKSPACE</span><h2>Run AgentScope locally</h2>
            <p>Install Python 3.12+, Node.js 24 with npm, Git, and <a href="https://docs.astral.sh/uv/getting-started/installation/">uv</a>. Native development uses SQLite and a deterministic investigator; Docker, Redis, and model credentials are optional.</p>
            <DocCode title="Start the local workspace">{`git clone --branch main https://github.com/Devesh36/AgentScope.git
cd AgentScope
npm run setup
npm run dev`}</DocCode>
            <p>Keep this terminal running. Setup installs the API, web app, editable SDK, and CLI, then applies database migrations. Open the dashboard in your browser:</p>
            <div className="docs-table-wrap"><table><thead><tr><th>Interface</th><th>Default address</th></tr></thead><tbody><tr><td>Dashboard</td><td><code>http://localhost:3000/dashboard</code></td></tr><tr><td>Public documentation</td><td><code>http://localhost:3000/docs</code></td></tr><tr><td>API and live schema</td><td><code>http://127.0.0.1:8000/docs</code></td></tr></tbody></table></div>
            <p>A new workspace starts empty. Create a project and a project ingestion API key in <strong>Settings → API keys</strong> to connect real agents, or use the labeled synthetic demo below to explore first.</p>
          </section>

          <section id="cli" className="docs-section">
            <span className="docs-section-number">03 / INTERACTIVE CLIENT</span><h2>Connect the CLI</h2>
            <p>Open a second terminal in the repository root and connect to the running API. The CLI uses the server&apos;s admin token file; project ingestion keys are used by the SDK instead.</p>
            <DocCode title="Connect from the checkout">{`.venv/bin/agentscope repl \\
  --url http://127.0.0.1:8000 \\
  --dashboard http://127.0.0.1:3000 \\
  --token-file .local/admin-token`}</DocCode>
            <p>The same CLI can monitor a local project with watch or connect to an existing server. Install it with uv:</p>
            <DocCode title="Install the standalone CLI">{`uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"
agentscope --version
agentscope repl --token-file /path/to/server/admin-token`}</DocCode>
            <p>Inside the REPL, <code>help</code> lists commands and <code>status</code> checks authenticated connectivity. Use <code>projects</code> to list workspaces and <code>use PROJECT_ID</code> to select one. <code>exit</code> closes the client and preserves server data.</p>
            <figure className="docs-terminal-shot"><a href="/docs-assets/cli-start.png" aria-label="Open the CLI connection screenshot at full size"><Image src="/docs-assets/cli-start.png" alt="Captured CLI session: AgentScope 0.2.0, help with available commands, and a successful connection to the local API." width={1200} height={661} unoptimized /></a><figcaption>Actual local CLI output, showing the command list and authenticated connection. Open the image to read it at full size.</figcaption></figure>
            <p>Keep token files private and outside version control. Remote servers require HTTPS. For Homebrew and additional connection options, read the <a href={`${repository}/blob/main/docs/cli.md`}>CLI reference</a>.</p>
          </section>

          <section id="demo" className="docs-section">
            <span className="docs-section-number">04 / FIRST INVESTIGATION</span><h2>Follow a signal to its evidence</h2>
            <p>Run <code>demo</code> inside the connected REPL. It creates a dedicated synthetic project, records a reproducible tool-loop scenario, waits for detection, and collects the investigation results. No paid model is called.</p>
            <DocCode title="Explore in the REPL">{`status
demo
investigation`}</DocCode>
            <figure className="docs-terminal-shot"><a href="/docs-assets/cli-demo.png" aria-label="Open the incident investigation screenshot at full size"><Image src="/docs-assets/cli-demo.png" alt="Captured synthetic demo: 25 persisted runs, a tool-loop incident, a completed investigation, eight evidence references, and a proposal with verification not started." width={1200} height={586} unoptimized /></a><figcaption>Captured against the running local API. The data is synthetic; the detection and persisted investigation are real. Your record IDs will differ.</figcaption></figure>
            <p>Select the printed project in the dashboard to inspect its traces, incident, and evidence. The recommendation is available for review; the demo command does not approve or execute it.</p>
            <h3>Practice intervention explicitly</h3><p>If you want to exercise the isolated demo control, use the IDs printed in your own session:</p>
            <DocCode title="Optional demo intervention">{`policy demo on
approve REMEDIATION_ID
execute REMEDIATION_ID
verify INVESTIGATION_ID`}</DocCode>
            <p><code>approve</code> authorizes a proposal. <code>execute</code> performs the separately approved demo action. <code>verify</code> waits for the 15-second observation window and evaluates stored follow-up runs. Execution alone does not confirm recovery.</p>
            <p>Other scenarios include <code>demo token_budget</code>, <code>demo tool_failure</code>, <code>demo stalled</code>, <code>demo unexpected_workflow</code>, and <code>demo healthy</code>. Each uses a separate project; the healthy scenario should produce no incident.</p>
          </section>

          <section id="sdk" className="docs-section">
            <span className="docs-section-number">05 / REAL TELEMETRY</span><h2>Instrument your Python agent</h2>
            <p>The local setup installs <code>agentscope-sdk</code>. Create a project API key in Settings, then configure <code>AGENTSCOPE_API_KEY</code> through your application&apos;s secret configuration. Use it to connect the SDK:</p>
            <DocCode title="Minimal Python integration">{`import os
from agentscope_sdk import AgentScope

with AgentScope(
    endpoint="http://127.0.0.1:8000",
    api_key=os.environ["AGENTSCOPE_API_KEY"],
    agent_name="calculator-agent",
) as scope:

    @scope.trace_tool
    def add(left, right):
        return left + right

    @scope.trace_agent
    def run():
        total = add(2, 3)
        scope.heartbeat("calculation complete")
        return total

    print(run())`}</DocCode>
            <p>The SDK registers the agent and exports nested spans in the background. The context manager closes and drains the exporter. Synchronous and asynchronous decorators are supported; arguments and results are represented by fingerprints rather than raw payloads.</p>
            <p>Record observed token usage when instrumenting a real LLM call. Estimated cost is shown only when pricing is known. The <a href={`${repository}/blob/main/examples/demo-agent/main.py`}>runnable async calculator example</a> shows tracing and progress events without a model call.</p>
          </section>

          <section id="interfaces" className="docs-section">
            <span className="docs-section-number">06 / INTEGRATIONS</span><h2>API, storage, and deployment</h2>
            <p>The dashboard proxies requests to FastAPI. Project API keys authorize telemetry ingestion and project resources; dashboard administration uses a separate server-side token. The API serves its complete schema at port 8000&apos;s <code>/docs</code>.</p>
            <div className="docs-table-wrap"><table><thead><tr><th>Integration</th><th>Endpoint</th></tr></thead><tbody><tr><td>Normalized telemetry</td><td><code>POST /api/v1/telemetry/events</code></td></tr><tr><td>OTLP JSON / protobuf</td><td><code>POST /v1/traces</code></td></tr><tr><td>Readiness</td><td><code>GET /health/ready</code></td></tr></tbody></table></div>
            <p>Native SQLite data and the generated admin token live in the ignored <code>.local/</code> directory. A transactional outbox keeps telemetry and processing durable. Run one API worker in local mode. PostgreSQL is supported with Alembic migrations; the optional Compose stack provides a documented local container workflow.</p>
            <div className="docs-note"><strong>Before sharing a workspace</strong><p>Configure dashboard authentication, HTTPS, and authenticated ingress before exposing the server outside a trusted local environment. Keep credentials private. This release does not yet provide multi-user organizations, production RBAC, distributed workers, or real-agent control adapters.</p></div>
            <div className="docs-resource-links"><a href={`${repository}/blob/main/docs/api.md`}>API reference <ArrowRight size={15} /></a><a href={`${repository}/blob/main/docs/local-containers.md`}>Container guide <ArrowRight size={15} /></a></div>
          </section>

          <section id="troubleshooting" className="docs-section">
            <span className="docs-section-number">07 / COMMON QUESTIONS</span><h2>Get back to a working setup</h2>
            <details open><summary>The CLI cannot connect</summary><p>Keep <code>npm run dev</code> running. Check that the API URL matches port 8000, then request <code>/health/ready</code>. For an existing server, keep it running. For automatic local startup, use watch.</p><DocCode title="Check API readiness">{`curl --fail http://127.0.0.1:8000/health/ready`}</DocCode></details>
            <details><summary>Authentication fails</summary><p>Use the admin token file from the server you are connecting to. A project API key cannot administer the CLI workspace. For SDK ingestion, use an active key from the intended project.</p></details>
            <details><summary>The dashboard is empty</summary><p>A fresh workspace has no runs. Select the correct project and instrument an agent, or explicitly run the synthetic demo. Check live/demo filters if records are hidden.</p></details>
            <details><summary>A proposal cannot execute</summary><p>Only the isolated synthetic adapter can execute actions. Enable demo control for the selected project, approve the proposal, then execute it separately. Real-agent recommendations remain advisory.</p></details>
            <details><summary>Recovery is still pending</summary><p>Wait for the 15-second observation window and inspect the persisted investigation with <code>verify</code>. Approval or a successful execution response is not a recovery measurement.</p></details>
          </section>
          <div className="docs-bottom"><Link href="/"><ArrowLeft size={15} /> Back to AgentScope</Link><a href={`${repository}/blob/main/README.md`}>Read the repository guide <ArrowRight size={15} /></a></div>
        </article>
      </div>
      <footer className="landing-footer"><Link className="landing-brand" href="/"><span><Activity size={18} /></span>AgentScope</Link><span>Observe. Understand. Verify.</span><a href={repository}>Source on GitHub <ArrowRight size={13} /></a></footer>
    </main>
  );
}
