import Link from "next/link";
import { Activity, ArrowDown, ArrowRight, Check, ChevronRight, GitBranch, Code2, LockKeyhole, Radar, ShieldCheck, Terminal, Waypoints } from "lucide-react";
import { InstallCommand } from "@/components/install-command";
import "./landing.css";

const repository = "https://github.com/Devesh36/AgentScope";

export default function LandingPage() {
  return (
    <main className="landing">
      <a className="landing-skip" href="#product">Skip to content</a>
      <header className="landing-nav">
        <Link href="/" className="landing-brand" aria-label="AgentScope home"><span><Activity size={21} /></span>AgentScope</Link>
        <nav aria-label="Site navigation"><a href="#product">Product</a><a href="#workflow">How it works</a><a href="#install">Install</a><Link href="/docs">Docs</Link></nav>
        <a href="#install" className="landing-nav-cta">Install CLI <ArrowRight size={15} /></a>
      </header>

      <section className="landing-hero" id="product">
        <div className="landing-hero-copy">
          <a className="landing-eyebrow" href="#install"><span /> OBSERVABILITY FOR AUTONOMOUS AGENTS <ChevronRight size={13} /></a>
          <h1>Your agents run.<br />Know <span>what happens.</span></h1>
          <p>Follow every trace, catch the unexpected, and turn incidents into evidence you can act on. One workspace for your agents, from execution to recovery.</p>
          <div className="landing-actions"><a className="landing-primary" href="#install">Get AgentScope <ArrowRight size={17} /></a><a className="landing-secondary" href="#demo">Explore the demo <Waypoints size={16} /></a></div>
          <div className="landing-hero-notes"><span><Check size={14} /> Runs locally</span><span><Check size={14} /> No model key required</span><span><Check size={14} /> You approve actions</span></div>
        </div>
        <div className="landing-console" aria-label="Illustrative synthetic demo preview">
          <div className="landing-console-top"><span><i /><i /><i /></span><span>agentscope / incident workspace</span><b>DEMO PREVIEW</b></div>
          <div className="landing-preview-header"><div><span className="landing-kicker">RUN EXPLORER</span><h2>research-agent <span>demo</span></h2></div><span className="landing-warning">Tool loop detected</span></div>
          <div className="landing-preview-stats"><div><span>Status</span><strong>Investigating</strong></div><div><span>Signal</span><strong>Repeated calls</strong></div><div><span>Source</span><strong>Synthetic</strong></div></div>
          <div className="landing-traces"><div className="landing-trace-label"><span>EXECUTION TRACE</span><span>0s <span>→</span> 12s</span></div>
            {[{ name: "agent.run", width: 94, left: 0, kind: "root" }, { name: "llm.generate", width: 24, left: 4, kind: "llm" }, { name: "tool.search", width: 17, left: 29, kind: "tool" }, { name: "tool.search", width: 17, left: 50, kind: "tool" }, { name: "tool.search", width: 17, left: 72, kind: "error" }].map((trace, i) => <div className={`landing-trace ${trace.kind}`} key={i}><code>{i ? "└ " : ""}{trace.name}</code><div><span style={{ width: `${trace.width}%`, marginLeft: `${trace.left}%` }} /></div></div>)}
          </div>
          <div className="landing-evidence"><div><Radar size={16} /><strong>Evidence-grounded finding</strong><span>3 referenced spans</span></div><p>Repeated tool invocations with matching inputs and no recorded progress.</p><footer><span>RECOMMENDATION READY</span><span><LockKeyhole size={12} /> Awaiting your approval</span></footer></div>
        </div>
      </section>

      <div className="landing-signal-strip"><span>Built for the whole agent lifecycle</span><div><Waypoints size={17} /> Traces</div><div><Radar size={17} /> Detection</div><div><GitBranch size={17} /> Investigation</div><div><ShieldCheck size={17} /> Verification</div></div>

      <section className="landing-section" id="workflow">
        <div className="landing-section-heading"><span className="landing-kicker">FROM SIGNAL TO RESOLUTION</span><h2>Less guessing.<br />More understanding.</h2><p>See what changed, inspect the evidence, and verify what worked. Every step stays connected to the execution that started it.</p></div>
        <div className="landing-feature-grid">
          <article><span className="landing-feature-icon"><Waypoints /></span><span className="landing-step">01 / OBSERVE</span><h3>The full execution story.</h3><p>Nested traces, tool calls, LLM usage, latency, and estimated cost. Bring real telemetry from your Python agents into one clear view.</p><div className="landing-feature-foot">Python SDK · run explorer</div></article>
          <article><span className="landing-feature-icon"><Radar /></span><span className="landing-step">02 / UNDERSTAND</span><h3>Incidents with evidence.</h3><p>Detect tool loops, failure storms, budget overruns, and stalled runs. Investigations link findings and competing hypotheses to persisted traces.</p><div className="landing-feature-foot">Deterministic detection · evidence references</div></article>
          <article><span className="landing-feature-icon"><ShieldCheck /></span><span className="landing-step">03 / VERIFY</span><h3>You stay in control.</h3><p>Review recommendations before approving. Practice isolated demo intervention, then measure recovery after an observation window.</p><div className="landing-feature-foot">Explicit approval · audited actions</div></article>
        </div>
        <p className="landing-scope"><LockKeyhole size={14} /> Real-agent remediation remains recommendation-only. Demo controls act only on labeled synthetic executions.</p>
      </section>

      <section className="landing-demo-section" id="demo">
        <div><span className="landing-kicker">TRY THE REAL PIPELINE</span><h2>Meet your next incident.<br />Before it meets you.</h2><p>Open the REPL, connect to your running server, and type <code>demo</code>. AgentScope records synthetic telemetry, detects an incident, and collects evidence. Approval and execution remain yours.</p><a href="#install" className="landing-text-link">Start with the CLI <ArrowDown size={15} /></a></div>
        <div className="landing-terminal"><div><Terminal size={15} /> AgentScope REPL <span>SYNTHETIC DEMO</span></div><pre><code><span className="landing-terminal-muted">$ </span>agentscope repl{"\n\n"}<span className="landing-terminal-prompt">agentscope&gt; </span>demo{"\n"}<span className="landing-terminal-muted">SYNTHETIC DEMO · tool_loop · seed 42{"\n"}Telemetry → detection → investigation{"\n"}Decision summary grounded in stored spans{"\n"}Proposal ready. No action executed.</span>{"\n\n"}<span className="landing-terminal-prompt">agentscope&gt; </span>help</code></pre><footer>Illustrative session · actual results come from your API</footer></div>
      </section>

      <section className="landing-install-section" id="install"><div><span className="landing-kicker">YOUR TERMINAL. YOUR WORKSPACE.</span><h2>Start seeing clearly.</h2><p>Install the CLI with uv or Homebrew, then connect to an existing AgentScope server. The SDK and local server are available in the repository.</p><a className="landing-text-link" href="/docs">Read the setup and demo guide <ArrowRight size={15} /></a></div><div><InstallCommand /><div className="landing-next-step"><span>Then open the REPL</span><code>agentscope repl</code><span>Also accepts <code>Agenscope Repl</code>. Set your server URL and admin token file using the setup guide.</span></div></div></section>

      <footer className="landing-footer"><Link className="landing-brand" href="/"><span><Activity size={18} /></span>AgentScope</Link><span>Observe. Understand. Verify.</span><a href={repository}><Code2 size={16} /> Source on GitHub <ArrowRight size={13} /></a></footer>
    </main>
  );
}
